"""Las pantallas de los comprobantes electrónicos que no son la factura.

Los cinco se ven igual: la lista, el formulario, la ficha con lo que respondió el SRI
y el RIDE. Lo que cambia —los campos, los títulos y cómo se llama la otra parte— lo
dice el registro (:mod:`comprobantes.registro`); aquí solo se pinta. Añadir un
comprobante nuevo es añadirlo al registro y escribir su formulario.
"""

from __future__ import annotations

from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from factec.django import conf, facturacion, services
from factec.django.documentos import (
    Factura,
    GuiaRemision,
    LiquidacionCompra,
    NotaDebito,
    Retencion,
)
from factec.django.models import EstadoComprobante, TipoComprobante
from factec.excepciones import ErrorFacturacion, ErrorRevision

from facturero.documentos_sri import (
    DOCUMENTOS_POR_CLAVE,
    ESTADOS,
    FORMATOS_RIDE,
    archivos_de,
    clave_por_partes,
    estado_de,
    iva_por_tarifa,
    totales_de,
)
from facturero.marco import marco, puede_emitir
from facturacion import auditoria
from personalize_options.decoradores import exigir_escritura, exigir_lectura

from . import forms, grupos, registro
from catalogos.models import CodigoRetencion

__all__ = [
    "accion", "buscar_codigos_retencion", "buscar_documentos", "documento", "ficha",
    "formulario", "items_de_documento", "lista", "ride",
]

#: Los comprobantes que *puede* modificar una nota, con su modelo, el campo de la otra
#: parte y el de su importe. La factura no está en el registro de los comprobantes
#: nuevos (vive en la aplicación de facturación), así que se dice aquí a mano.
MODIFICABLES = (
    (TipoComprobante.FACTURA.value, Factura, "receptor", "total"),
    (TipoComprobante.LIQUIDACION_COMPRA.value, LiquidacionCompra, "proveedor", "total"),
    (TipoComprobante.NOTA_DEBITO.value, NotaDebito, "receptor", "total"),
    (TipoComprobante.GUIA_REMISION.value, GuiaRemision, "", ""),
    (TipoComprobante.COMPROBANTE_RETENCION.value, Retencion, "sujeto_retenido", "total_retenido"),
)

#: Los que llevan líneas, que son los que se pueden devolver con una nota de crédito.
CON_LINEAS = {
    TipoComprobante.FACTURA.value: Factura,
    TipoComprobante.LIQUIDACION_COMPRA.value: LiquidacionCompra,
}


def _partes_del_numero(numero: str) -> Optional[tuple[str, str, str]]:
    """Un número de comprobante en sus tres partes (estab, punto de emisión, secuencial).

    Se acepta con guiones (``001-001-000000123``) o de corrido (``001001000000123``).
    """
    limpio = (numero or "").replace("-", "")
    if len(limpio) != 15 or not limpio.isdigit():
        return None
    return limpio[:3], limpio[3:6], limpio[6:]


def _numero_limpio(valor: Any) -> str:
    """Un número sin ceros de relleno: ``5.000000`` se lee ``5`` y ``10.500000``, ``10.5``.

    La columna de la cantidad es estrecha, así que lo que se pone en la tabla tiene que
    caber: con los ceros del SRI no se leía.
    """
    texto = str(valor)
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


@login_required
def items_de_documento(request: HttpRequest) -> JsonResponse:
    """Las líneas del comprobante que se modifica, para devolverlas tal cual.

    Con el tipo y el número que dejó el buscador de comprobantes, devuelve sus líneas
    —con su código, su cantidad y su precio— para que la nota de crédito devuelva
    exactamente lo que se vendió.
    """
    tipo = request.GET.get("tipo") or ""
    numero = request.GET.get("numero") or ""
    texto = (request.GET.get("q") or "").strip()

    modelo = CON_LINEAS.get(tipo)
    partes = _partes_del_numero(numero)
    if modelo is None or partes is None:
        return JsonResponse({"resultados": []})

    objeto = (
        modelo.objects.filter(
            comprobante__estab=partes[0],
            comprobante__pto_emi=partes[1],
            comprobante__secuencial=partes[2],
        )
        .order_by("-id")
        .first()
    )
    if objeto is None:
        return JsonResponse({"resultados": []})

    lineas = objeto.detalles.all()
    if texto:
        lineas = lineas.filter(
            Q(descripcion__icontains=texto) | Q(codigo_principal__icontains=texto)
        )
    return JsonResponse(
        {
            "resultados": [
                {
                    "pk": linea.producto_id or "",
                    "codigo_principal": linea.codigo_principal,
                    "descripcion": linea.descripcion,
                    "cantidad": _numero_limpio(linea.cantidad),
                    "precio_unitario": _numero_limpio(linea.precio_unitario),
                    "descuento": _numero_limpio(linea.descuento),
                    "unidad_medida": linea.unidad_medida,
                    "codigo_porcentaje_iva": linea.codigo_porcentaje_iva,
                }
                for linea in lineas[:50]
            ]
        },
        json_dumps_params={"ensure_ascii": False},
    )


def _documento(clave: str) -> registro.Documento:
    """El comprobante que se está viendo, por su clave de la dirección."""
    documento = registro.POR_CLAVE.get(clave)
    if documento is None:
        raise Http404(f"No hay comprobantes de tipo «{clave}».")
    return documento


def _opcion(clave: str) -> str:
    """La opción del menú que gobierna este comprobante.

    La dirección usa guiones (``notas-credito``) y las opciones del paquete, guiones
    bajos (``notas_credito``): se traduce aquí para no repetir el mapa.
    """
    return clave.replace("-", "_")


def _puede_ver(request: HttpRequest, clave: str) -> None:
    """Corta si este usuario no puede leer este tipo de comprobante."""
    exigir_lectura(request, _opcion(clave))


def _puede_tocar(request: HttpRequest, clave: str) -> None:
    """Corta si este usuario no puede emitir o corregir este tipo de comprobante."""
    exigir_escritura(request, _opcion(clave))


def _listado(documento: registro.Documento) -> Any:
    """Lo que se ve en la lista, ya resuelto para la plantilla."""
    consulta = documento.modelo.objects.select_related("comprobante")
    if documento.campo_contraparte:
        consulta = consulta.select_related(documento.campo_contraparte)
    return consulta


def _numero(objeto: Any) -> str:
    """El número del comprobante, o «sin emitir» mientras sea un borrador."""
    if objeto.comprobante_id:
        return objeto.comprobante.numero_comprobante
    return "Sin emitir"


def _filas(consulta: Any, documento: registro.Documento) -> list[dict[str, Any]]:
    """Una fila de la lista, con lo justo para pintarla."""
    objetos = list(consulta)
    usuarios = auditoria.mapa(objetos)
    return [
        {
            "objeto": objeto,
            "numero": _numero(objeto),
            "contraparte": documento.contraparte(objeto),
            "importe": documento.importe(objeto) if documento.importe else None,
            "registro": objeto.comprobante if objeto.comprobante_id else None,
            "estado": estado_de(objeto.comprobante if objeto.comprobante_id else None),
            "usuario": usuarios.get(objeto.pk),
        }
        for objeto in objetos
    ]


# ------------------------------------------------------------------- la lista


@login_required
def lista(request: HttpRequest, clave: str) -> HttpResponse:
    """Los comprobantes de un tipo, lo más nuevo primero, con su buscador."""
    _puede_ver(request, clave)
    documento = _documento(clave)
    consulta = _listado(documento)

    buscado = (request.GET.get("q") or "").strip()
    estado = request.GET.get("estado") or ""
    if buscado:
        filtros = Q(secuencial__icontains=buscado) | Q(
            comprobante__clave_acceso__icontains=buscado
        )
        if documento.campo_contraparte:
            filtros |= Q(**{f"{documento.campo_contraparte}__razon_social__icontains": buscado})
            filtros |= Q(**{f"{documento.campo_contraparte}__identificacion__icontains": buscado})
        consulta = consulta.filter(filtros).distinct()
    if estado == "sin_emitir":
        consulta = consulta.filter(comprobante__isnull=True)
    elif estado:
        consulta = consulta.filter(comprobante__estado=estado)

    filas = _filas(consulta[:200], documento)
    contexto = {
        **marco(request),
        "documento": documento,
        "filas": filas,
        "cuantas": len(filas),
        "filtros": {"q": buscado, "estado": estado},
        "estados": ESTADOS,
        "aviso_emisor": puede_emitir(conf.configuracion_activa()),
    }
    return render(request, "comprobantes/lista.html", contexto)


# --------------------------------------------------------------- el formulario


@login_required
def buscar_codigos_retencion(request: HttpRequest) -> JsonResponse:
    """La tabla de retenciones del SRI, para elegir el código en su ventana.

    Son más de cien conceptos con el texto completo: se buscan por código o por lo
    que se retiene y se eligen de la lista, en vez de desplegar una lista enorme
    dentro del comprobante.
    """
    texto = (request.GET.get("q") or "").strip()
    consulta = CodigoRetencion.objects.all()
    if texto:
        consulta = consulta.filter(Q(codigo__icontains=texto) | Q(concepto__icontains=texto))

    filas = [
        {
            "codigo": codigo.codigo,
            "concepto": codigo.concepto,
            "impuesto": codigo.impuesto,
            "impuesto_nombre": codigo.get_impuesto_display(),
            "porcentaje": str(codigo.porcentaje) if codigo.porcentaje is not None else "",
            "porcentaje_texto": codigo.porcentaje_texto,
            "como_porcentaje": codigo.como_porcentaje,
            "etiqueta": codigo.etiqueta,
        }
        for codigo in consulta[:60]
    ]
    return JsonResponse(
        {"resultados": filas}, json_dumps_params={"ensure_ascii": False}
    )


@login_required
def buscar_documentos(request: HttpRequest) -> JsonResponse:
    """Los comprobantes ya autorizados, para elegir el que modifica una nota.

    Se filtra por fecha —que es lo que más se usa—, por tipo de comprobante y por lo
    que se escriba (cliente, RUC, número o clave). Devuelve lo justo para pintar la
    tabla del buscador.
    """
    texto = (request.GET.get("q") or "").strip()
    desde = parse_date(request.GET.get("desde") or "")
    hasta = parse_date(request.GET.get("hasta") or "")
    tipo = request.GET.get("tipo") or ""

    filas = []
    for codigo, modelo, campo, importe in MODIFICABLES:
        if tipo and tipo != codigo:
            continue
        consulta = modelo.objects.filter(comprobante__estado=EstadoComprobante.AUTORIZADO)
        if desde:
            consulta = consulta.filter(fecha_emision__gte=desde)
        if hasta:
            consulta = consulta.filter(fecha_emision__lte=hasta)
        if texto:
            filtros = Q(comprobante__secuencial__icontains=texto) | Q(
                comprobante__clave_acceso__icontains=texto
            )
            if campo:
                filtros |= Q(**{f"{campo}__razon_social__icontains": texto})
                filtros |= Q(**{f"{campo}__identificacion__icontains": texto})
            consulta = consulta.filter(filtros)

        for objeto in consulta.order_by("-fecha_emision", "-id")[:20]:
            comprobante = objeto.comprobante
            filas.append(
                {
                    "tipo": codigo,
                    "tipo_nombre": forms.DOCUMENTOS_QUE_MODIFICA[codigo],
                    "numero": f"{comprobante.estab}-{comprobante.pto_emi}-{comprobante.secuencial}",
                    "fecha": objeto.fecha_emision.isoformat() if objeto.fecha_emision else "",
                    "contraparte_campo": campo,
                    "contraparte_pk": getattr(objeto, f"{campo}_id", "") if campo else "",
                    "contraparte": (
                        getattr(getattr(objeto, campo), "razon_social", "") if campo else ""
                    ),
                    "total": str(getattr(objeto, importe, "")) if importe else "",
                }
            )

    filas.sort(key=lambda fila: fila["fecha"], reverse=True)
    return JsonResponse(
        {
            "resultados": filas[:30],
            "tipos": forms.DOCUMENTOS_QUE_MODIFICA,
        },
        json_dumps_params={"ensure_ascii": False},
    )


def _con_la_contraparte(documento: registro.Documento, datos: Any) -> Any:
    """Le pone a la nota el cliente del comprobante que modifica, si no lo trae.

    En estas notas el cliente no se elige a mano: sale del comprobante. Así no se puede
    emitir una nota al cliente que no es, ni siquiera si el navegador no hizo su parte.
    """
    campo = documento.campo_contraparte
    if not campo or datos.get(campo):
        return datos

    codigo = datos.get("cod_doc_modificado") or ""
    partes = _partes_del_numero(datos.get("num_doc_modificado") or "")
    if partes is None:
        return datos

    for codigo_documento, modelo, campo_modelo, _ in MODIFICABLES:
        if codigo_documento != codigo or not campo_modelo:
            continue
        objeto = modelo.objects.filter(
            comprobante__estab=partes[0],
            comprobante__pto_emi=partes[1],
            comprobante__secuencial=partes[2],
        ).first()
        if objeto is None:
            continue
        copia = datos.copy()
        copia[campo] = str(getattr(objeto, f"{campo_modelo}_id", "") or "")
        return copia
    return datos


@login_required
def formulario(request: HttpRequest, clave: str, pk: Optional[int] = None) -> HttpResponse:
    """El formulario del comprobante: la cabecera, sus filas y sus totales."""
    _puede_ver(request, clave)
    if request.method == "POST":
        _puede_tocar(request, clave)
    documento = _documento(clave)
    objeto = get_object_or_404(documento.modelo, pk=pk) if pk else documento.modelo()

    if pk and objeto.autorizado:
        messages.info(
            request,
            f"Esta {documento.titulo.lower()} ya está autorizada por el SRI: se puede "
            "mirar, pero no volver a emitir.",
        )
        return redirect("comprobantes:ficha", clave=clave, pk=objeto.pk)

    # La cabecera y, si el comprobante lleva líneas, sus tablas.
    datos = request.POST or None
    if request.method == "POST" and documento.hijo is None:
        datos = _con_la_contraparte(documento, request.POST)
    form = documento.formulario(datos, instance=objeto)
    formset = (
        documento.lineas(datos, instance=objeto, prefix="lineas") if documento.lineas else None
    )
    formset2 = (
        documento.lineas2(datos, instance=objeto, prefix="lineas2")
        if documento.lineas2
        else None
    )
    # Los que se repiten por cabeceras (la guía, la retención) llevan sus filas dentro
    # de cada una, en vez de un solo bloque colgado del comprobante.
    conjuntos = grupos.Grupos(documento, datos, objeto) if grupos.hay_grupos(documento) else None

    if request.method == "POST":
        piezas = [
            form.is_valid(),
            formset is None or formset.is_valid(),
            formset2 is None or formset2.is_valid(),
            conjuntos is None or conjuntos.valido,
        ]
        if all(piezas):
            objeto = _guardar(
                documento, form, formset, formset2, conjuntos, usuario=request.user
            )
            if request.POST.get("accion") == "emitir":
                return _emitir(request, documento, objeto)
            messages.success(
                request,
                f"{documento.titulo} guardada. Cuando esté lista, se emite al SRI.",
            )
            return redirect("comprobantes:editar", clave=clave, pk=objeto.pk)
        messages.error(request, "Revise lo que está marcado en rojo.")

    contexto = {
        **marco(request),
        "documento": documento,
        "objeto": objeto,
        "formulario": form,
        "formset": formset,
        "formset2": formset2,
        "conjuntos": conjuntos,
        "muestras": grupos.muestras(documento) if conjuntos is not None else [],
        "contraparte": (
            getattr(objeto, documento.campo_contraparte)
            if documento.campo_contraparte and objeto.pk
            else None
        ),
        "aviso_emisor": puede_emitir(conf.configuracion_activa()),
        **_cuerpo(objeto),
        **_totales(objeto),
    }
    return render(request, "comprobantes/formulario.html", contexto)


def _guardar(
    documento: registro.Documento,
    form: Any,
    formset: Any,
    formset2: Any,
    conjuntos: Any,
    usuario: Any = None,
) -> Any:
    """Guarda la cabecera y, con ella, sus cabeceras repetibles y sus filas.

    Todo dentro de una transacción: si una fila no entra, no queda un comprobante a
    medias en la base.
    """
    with transaction.atomic():
        objeto = form.save()
        if conjuntos is not None:
            conjuntos.save()
        for conjunto in (formset, formset2):
            if conjunto is None:
                continue
            conjunto.instance = objeto
            conjunto.save()
        auditoria.registrar(objeto, usuario)
    return objeto


def _totales(objeto: Any) -> dict[str, Any]:
    """Los totales del comprobante, si los tiene (la nota de débito no lleva líneas)."""
    if not hasattr(objeto, "totales") or not objeto.pk:
        return {}
    return {
        "totales": totales_de(objeto),
        "iva_por_tarifa": iva_por_tarifa(objeto.detalles.all()),
    }


def _cuerpo(objeto: Any) -> dict[str, Any]:
    """Las filas del comprobante, con el nombre que tengan (líneas, motivos, bienes…)."""
    datos: dict[str, Any] = {}
    for nombre in ("detalles", "motivos", "destinatarios", "docs_sustento"):
        if hasattr(objeto, nombre) and objeto.pk:
            datos[nombre] = getattr(objeto, nombre).all()
    return datos


def _emitir(request: HttpRequest, documento: registro.Documento, objeto: Any) -> HttpResponse:
    """Emite de verdad: firma, envía al SRI y cuenta lo que pasó."""
    clave = documento.clave
    try:
        registro_emitido = facturacion.emitir(objeto, encolar=False)
    except ErrorRevision as exc:
        # El paquete revisa antes de firmar: el mensaje ya explica qué falta.
        messages.error(request, f"No se emitió nada: {exc}")
        return redirect("comprobantes:editar", clave=clave, pk=objeto.pk)
    except ErrorFacturacion as exc:
        messages.error(request, f"Falló la emisión: {exc}")
        return redirect("comprobantes:ficha", clave=clave, pk=objeto.pk)

    if registro_emitido.autorizado:
        messages.success(
            request,
            f"{documento.titulo} {registro_emitido.secuencial} autorizada por el SRI. "
            f"Autorización {registro_emitido.numero_autorizacion}.",
        )
        if documento.al_autorizar is not None:
            documento.al_autorizar(objeto, request.user)
    elif registro_emitido.mensajes:
        for aviso in registro_emitido.mensajes:
            messages.warning(request, aviso.get("mensaje") or str(aviso))
    else:
        messages.warning(
            request,
            f"El comprobante quedó en {estado_de(registro_emitido)}. "
            "Puede reintentar el envío desde su ficha.",
        )
    return redirect("comprobantes:ficha", clave=clave, pk=objeto.pk)


# -------------------------------------------------------- la ficha y el RIDE


def _contexto_comprobante(request: HttpRequest, documento: registro.Documento, pk: int) -> dict[str, Any]:
    """Lo que necesitan la ficha y el RIDE: el comprobante y lo que dejó el envío."""
    objeto = get_object_or_404(
        documento.modelo.objects.select_related("comprobante"), pk=pk
    )
    registro_sri = objeto.comprobante if objeto.comprobante_id else None
    contraparte = (
        getattr(objeto, documento.campo_contraparte)
        if documento.campo_contraparte
        else None
    )
    return {
        **marco(request),
        "documento": documento,
        "objeto": objeto,
        "contraparte": contraparte,
        "registro": registro_sri,
        "estado": estado_de(registro_sri),
        "documentos": archivos_de(registro_sri),
        "mensajes_sri": (registro_sri.mensajes if registro_sri else []) or [],
        "clave_por_partes": clave_por_partes(registro_sri.clave_acceso if registro_sri else ""),
        "registro_usuario": auditoria.de(objeto),
        **_cuerpo(objeto),
        **_totales(objeto),
    }


@login_required
def ficha(request: HttpRequest, clave: str, pk: int) -> HttpResponse:
    """El comprobante y lo que respondió el SRI, con las acciones sobre él."""
    _puede_ver(request, clave)
    documento = _documento(clave)
    contexto = _contexto_comprobante(request, documento, pk)
    # En pantalla las tablas son las del comprobante (las mismas que en la factura).
    contexto["clase_tabla"] = "libro-detalles"
    return render(request, "comprobantes/ficha.html", contexto)


@login_required
def ride(request: HttpRequest, clave: str, pk: int) -> HttpResponse:
    """El comprobante listo para imprimir: en hoja A4 o en tíquet de 80 mm."""
    _puede_ver(request, clave)
    documento = _documento(clave)
    formato = request.GET.get("formato") or "a4"
    if formato not in FORMATOS_RIDE:
        formato = "a4"

    contexto = _contexto_comprobante(request, documento, pk)
    contexto.update(
        {
            "formato": formato,
            "es_ticket": formato == "t80",
            "hoja": FORMATOS_RIDE[formato],
            # Se pidió imprimir desde el diálogo: la hoja se imprime sola al abrirse.
            "imprimir_ya": bool(request.GET.get("imprimir")),
        }
    )
    return render(request, "comprobantes/ride.html", contexto)


@login_required
def documento_sri(request: HttpRequest, clave: str, pk: int, cual: str) -> HttpResponse:
    """Un documento del comprobante: el XML o una respuesta del SRI.

    Se sirve lo guardado en la base (no del disco), para poder mirarlo o guardarlo
    aunque los archivos no se conserven. Con ``?descargar=1`` baja como archivo.
    """
    _puede_ver(request, clave)
    documento = _documento(clave)
    objeto = get_object_or_404(documento.modelo, pk=pk)
    registro_sri = objeto.comprobante if objeto.comprobante_id else None
    archivo = DOCUMENTOS_POR_CLAVE.get(cual)
    contenido = ""
    if registro_sri is not None and archivo is not None:
        contenido = getattr(registro_sri, archivo["campo"], "") or ""

    if not archivo or not contenido:
        messages.error(request, f"Todavía no hay «{cual}» en este comprobante.")
        return redirect("comprobantes:ficha", clave=clave, pk=pk)

    respuesta = HttpResponse(contenido, content_type=f"{archivo['tipo']}; charset=utf-8")
    nombre = f"{registro_sri.numero_comprobante}_{archivo['archivo']}"
    descarga = "attachment" if request.GET.get("descargar") else "inline"
    respuesta["Content-Disposition"] = f'{descarga}; filename="{nombre}"'
    return respuesta


@login_required
@require_POST
def accion(request: HttpRequest, clave: str, pk: int, que: str) -> HttpResponse:
    """Reintentar el envío, preguntar al SRI o rehacer la fecha."""
    _puede_ver(request, clave)
    if que != "consultar":
        _puede_tocar(request, clave)
    documento = _documento(clave)
    objeto = get_object_or_404(documento.modelo, pk=pk)
    registro_sri = objeto.comprobante if objeto.comprobante_id else None
    if registro_sri is None:
        messages.error(request, "Este comprobante todavía no se ha emitido.")
        return redirect("comprobantes:ficha", clave=clave, pk=pk)

    try:
        if que == "reintentar":
            registro_sri = facturacion.reintentar(objeto, encolar=False) or registro_sri
            registro_sri.refresh_from_db()
            messages.info(request, f"Reintento hecho: {estado_de(registro_sri)}.")
        elif que == "consultar":
            services.autorizar(registro_sri)
            registro_sri.refresh_from_db()
            messages.info(request, f"El SRI responde: {estado_de(registro_sri)}.")
        elif que == "fecha":
            services.actualizar_fecha(registro_sri)
            messages.success(request, "Comprobante refechado al día de hoy (la clave cambió).")
        else:
            messages.error(request, "Esa acción no existe.")
    except Exception as exc:  # noqa: BLE001 - se le cuenta al usuario, tal cual
        messages.error(request, f"No se pudo: {type(exc).__name__}: {exc}")
    return redirect("comprobantes:ficha", clave=clave, pk=pk)
