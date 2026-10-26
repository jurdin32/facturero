"""La interfaz para facturar: emitir y seguir los comprobantes.

Es una capa fina sobre el paquete: quien firma, envía y consulta al SRI es
``factec``; aquí solo se pinta. Las pantallas son tres: la lista, el formulario de
facturación (que se parece al documento que produce) y la factura ya emitida, con lo
que respondió el SRI.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from factec.catalogos import PORCENTAJE_IVA
from factec.django import conf, facturacion, services
from factec.django.documentos import (
    OPCIONES_TIPO_IDENTIFICACION,
    Cliente,
    Factura,
    Producto,
)
from factec.excepciones import ErrorFacturacion, ErrorRevision
from factec.sri.fechas import hoy_en_ecuador
from caja import servicios as caja_servicios

from facturero.codigo_barras import svg as codigo_de_barras
from facturero.documentos_sri import (
    DOCUMENTOS_POR_CLAVE,
    ESTADOS,
    FORMATOS_RIDE,
    archivos_de,
    clave_por_partes,
    estado_de,
    informacion_adicional_de,
    iva_por_tarifa,
    subtotales_por_tarifa,
    totales_de,
)
from facturero.marco import marco, puede_emitir, primera_pantalla
from inventario.servicios import descontar_de_la_factura

from configuracion.models import LogoEmisor

from personalize_options.decoradores import exigir_escritura, requiere_lectura
from personalize_options.permisos import de_la_peticion

from . import auditoria
from . import tablero as consultas
from .forms import DetallesDeFactura, FormularioFactura

__all__ = [
    "facturas", "facturar", "factura", "emitir", "accion", "xml", "ride", "producto",
    "buscar_clientes", "buscar_productos",
]


# --------------------------------------------------------------------- el marco


# ------------------------------------------------------------------ el tablero


@login_required
def tablero(request: HttpRequest) -> HttpResponse:
    """Lo primero que se ve: lo que se ha facturado, lo que pide atención y lo
    que se puede hacer ahora mismo."""
    # El tablero es la puerta de entrada, pero enseña las ventas de todo el negocio:
    # quien no puede leerlo pasa a la primera pantalla que sí tiene.
    permisos = de_la_peticion(request)
    if not permisos.puede_leer("tablero"):
        destino = primera_pantalla(permisos)
        if destino is None:
            raise PermissionDenied("Este usuario no tiene ninguna opción asignada.")
        return redirect(destino)

    hoy, _ = consultas.hoy_y_ayer()
    try:
        dias = int(request.GET.get("dias") or 14)
    except ValueError:
        dias = 14
    if dias not in consultas.PERIODOS:
        dias = 14

    ventas = consultas.ventas_por_dia(hoy, dias)

    orden = request.GET.get("orden") or consultas.ORDEN_POR_OMISION
    if orden not in {clave for clave, _ in consultas.ORDENES}:
        orden = consultas.ORDEN_POR_OMISION

    contexto = {
        **marco(request),
        "hoy": hoy,
        "contadores": consultas.contadores(hoy),
        "ventas": ventas,
        "periodos": consultas.PERIODOS,
        "dias": dias,
        "movidos": consultas.mas_movidos(hoy, dias, orden),
        "orden": orden,
        "ordenes": consultas.ORDENES,
        "bajo_minimo": consultas.bajo_minimo(),
        "aviso_emisor": puede_emitir(conf.configuracion_activa()),
    }
    return render(request, "facturacion/tablero.html", contexto)


# ------------------------------------------------------------------ la lista


@login_required
@requiere_lectura("facturas")
def facturas(request: HttpRequest) -> HttpResponse:
    """Las facturas, lo más nuevas primero, con filtros de trabajo."""
    lista = (
        Factura.objects.select_related("receptor", "comprobante")
        .order_by("-fecha_emision", "-pk")
    )

    estado = request.GET.get("estado") or ""
    desde = request.GET.get("desde") or ""
    hasta = request.GET.get("hasta") or ""
    cliente = request.GET.get("cliente") or ""
    texto = (request.GET.get("q") or "").strip()

    if desde:
        lista = lista.filter(fecha_emision__gte=desde)
    if hasta:
        lista = lista.filter(fecha_emision__lte=hasta)
    if cliente:
        lista = lista.filter(receptor_id=cliente)
    if texto:
        lista = lista.filter(
            Q(receptor__razon_social__icontains=texto)
            | Q(receptor__identificacion__icontains=texto)
            | Q(comprobante__clave_acceso__icontains=texto)
            | Q(comprobante__secuencial__icontains=texto)
            | Q(detalles__descripcion__icontains=texto)
        ).distinct()
    if estado == "sin_emitir":
        lista = lista.filter(comprobante__isnull=True)
    elif estado:
        lista = lista.filter(comprobante__estado=estado)

    # La lista viene entera: el navegador busca, ordena y pagina con la tabla de Metro.
    facturas = list(lista.prefetch_related("detalles"))
    registros = auditoria.mapa(facturas)
    for factura in facturas:
        factura.registro_usuario = registros.get(factura.pk)

    contexto = {
        **marco(request),
        "facturas": facturas,
        "filtros": {"estado": estado, "desde": desde, "hasta": hasta, "cliente": cliente, "q": texto},
        "estados": ESTADOS,
        "clientes": Cliente.objects.order_by("razon_social"),
        "cuantas": len(facturas),
    }
    return render(request, "facturacion/facturas.html", contexto)


# -------------------------------------------------------------- facturar


@login_required
@requiere_lectura("facturar")
def facturar(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """El formulario de facturación: se parece al documento que va a salir."""
    factura = get_object_or_404(Factura, pk=pk) if pk else Factura(fecha_emision=hoy_en_ecuador())
    if pk and factura.autorizado:
        messages.info(
            request,
            "Esta factura ya está autorizada por el SRI: se puede mirar, pero no volver a emitir.",
        )
        return redirect("facturacion:factura", pk=factura.pk)

    # Toda venta entra en el arqueo del turno: sin caja abierta no se factura. Así el
    # efectivo que se cobra tiene dónde constar y el cierre del día cuadra.
    if caja_servicios.sesion_abierta(request.user) is None:
        messages.warning(
            request,
            "Para facturar primero hay que abrir la caja del turno: cada venta queda "
            "en su arqueo.",
        )
        return redirect("caja:tablero")

    if request.method == "POST":
        exigir_escritura(request, "facturar")
        formulario = FormularioFactura(request.POST, instance=factura)
        detalles = DetallesDeFactura(request.POST, instance=factura)
        if formulario.is_valid() and detalles.is_valid():
            faltantes = _stock_faltante(detalles)
            if not _hay_lineas(detalles):
                messages.error(request, "Añada al menos un producto o servicio: la factura no sale vacía.")
            elif faltantes:
                messages.error(
                    request,
                    "No hay existencia suficiente: " + " ".join(faltantes),
                )
            else:
                factura = formulario.save()
                detalles.instance = factura
                detalles.save()
                auditoria.registrar(factura, request.user)
                if request.POST.get("accion") == "emitir":
                    return _emitir(request, factura)
                messages.success(request, "Borrador guardado. Cuando esté listo, se emite.")
                return redirect("facturacion:editar_factura", pk=factura.pk)
        else:
            messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        inicial = {}
        # Se puede llegar desde el catálogo con el cliente ya elegido.
        elegido = request.GET.get("cliente")
        if elegido and not factura.pk:
            inicial["receptor"] = elegido
        formulario = FormularioFactura(instance=factura, initial=inicial)
        detalles = DetallesDeFactura(instance=factura)

    contexto = {
        **marco(request),
        "formulario": formulario,
        "detalles": detalles,
        "factura": factura,
        "aviso_emisor": puede_emitir(conf.configuracion_activa()),
        "tipos_identificacion": dict(OPCIONES_TIPO_IDENTIFICACION),
        # De una factura sin guardar no se pueden leer las líneas: se empieza en cero.
        "totales": totales_de(factura) if factura.pk else {},
        "productos": Producto.objects.filter(activo=True).order_by("descripcion"),
        # Las tarifas de IVA con las que el paquete calcula, para la cuenta de la hoja.
        "porcentajes_iva": {codigo: str(tasa) for codigo, tasa in PORCENTAJE_IVA.items()},
    }
    return render(request, "facturacion/facturar.html", contexto)


def _hay_lineas(detalles: DetallesDeFactura) -> bool:
    """¿La factura lleva algo? Una línea vacía o marcada para borrar no cuenta."""
    for linea in detalles.forms:
        if not linea.cleaned_data or linea.cleaned_data.get("DELETE"):
            continue
        if linea.cleaned_data.get("descripcion") or linea.cleaned_data.get("producto"):
            return True
    return False


def _stock_faltante(detalles: DetallesDeFactura) -> list[str]:
    """Los bienes que se piden por encima de lo que hay en inventario.

    Los servicios y las líneas escritas a mano no llevan existencia. Se suman todas
    las líneas del mismo producto antes de comparar: dos líneas de 3 con 5 en
    existencia tampoco pasan.
    """
    pedidos: dict[Producto, Decimal] = {}
    for linea in detalles.forms:
        datos = getattr(linea, "cleaned_data", None)
        if not datos or datos.get("DELETE"):
            continue
        producto = datos.get("producto")
        cantidad = datos.get("cantidad") or Decimal("0")
        if not producto or producto.es_servicio or cantidad <= 0:
            continue
        pedidos[producto] = pedidos.get(producto, Decimal("0")) + cantidad

    faltantes = []
    for producto, cantidad in pedidos.items():
        existencia = getattr(producto, "existencia", None)
        hay = existencia.cantidad if existencia is not None else Decimal("0")
        if cantidad > hay:
            faltantes.append(
                f"«{producto.descripcion}»: se piden {cantidad:g} y hay {hay:g}."
            )
    return faltantes


def _descontar_inventario(request: HttpRequest, factura: Factura) -> None:
    """Saca del inventario lo que acaba de facturarse (si así está configurado).

    No se avisa de que el libro se movió: el descuento es lo que se espera al
    facturar y un aviso más solo tapa el de la factura. Lo que sí se avisa es de un
    producto que quedó en negativo, que eso hay que mirarlo.
    """
    movimientos = descontar_de_la_factura(factura, usuario=request.user)
    for movimiento in movimientos:
        existencia = getattr(movimiento.producto, "existencia", None)
        if existencia is not None and existencia.cantidad < 0:
            messages.warning(
                request,
                f"Quedan {existencia.cantidad} de {movimiento.producto.descripcion}: "
                "revise si falta cargar una entrada.",
            )


def _emitir(request: HttpRequest, factura: Factura) -> HttpResponse:
    """Emite de verdad: firma, envía al SRI y cuenta lo que pasó."""
    try:
        registro = facturacion.emitir(factura, encolar=False)
    except ErrorRevision as exc:
        # El paquete revisa antes de firmar: el mensaje ya explica qué falta.
        messages.error(request, f"No se emitió nada: {exc}")
        return redirect("facturacion:editar_factura", pk=factura.pk)
    except ErrorFacturacion as exc:
        messages.error(request, f"Falló la emisión: {exc}")
        return redirect("facturacion:factura", pk=factura.pk)

    if registro.autorizado:
        messages.success(
            request,
            f"Factura {registro.secuencial} autorizada por el SRI. "
            f"Autorización {registro.numero_autorizacion}.",
        )
        _descontar_inventario(request, factura)
        try:
            factura.refresh_from_db(fields=["comprobante"])
            caja_servicios.registrar_ingreso_factura(factura, request.user)
        except Exception:  # noqa: BLE001 - la caja no puede tumbar la emisión
            logging.getLogger(__name__).exception(
                "No se pudo registrar el cobro en efectivo de la factura %s", factura.pk
            )
    elif registro.mensajes:
        for aviso in registro.mensajes:
            messages.warning(request, aviso.get("mensaje") or str(aviso))
    else:
        messages.warning(
            request,
            f"La factura quedó en {ESTADOS.get(registro.estado, registro.estado)}. "
            "Puede reintentar el envío desde su ficha.",
        )
    return redirect("facturacion:factura", pk=factura.pk)


# ------------------------------------------------------------- una factura


@login_required
@requiere_lectura("facturas")
def factura(request: HttpRequest, pk: int) -> HttpResponse:
    """La factura y lo que respondió el SRI, con las acciones sobre el comprobante."""
    factura = get_object_or_404(
        Factura.objects.select_related("receptor", "comprobante"), pk=pk
    )
    registro = factura.comprobante if factura.comprobante_id else None

    contexto = {
        **marco(request),
        "factura": factura,
        "registro": registro,
        "detalles": factura.detalles.all(),
        "totales": totales_de(factura),
        "estado": estado_de(registro),
        "mensajes_sri": (registro.mensajes if registro else []) or [],
        "documentos": archivos_de(registro),
        "iva_por_tarifa": iva_por_tarifa(factura.detalles.all()),
        "clave_por_partes": clave_por_partes(registro.clave_acceso if registro else ""),
        "registro_usuario": auditoria.de(factura),
        "logo": LogoEmisor.de(conf.configuracion_activa()),
    }
    return render(request, "facturacion/factura.html", contexto)


@login_required
@requiere_lectura("facturas")
def ride(request: HttpRequest, pk: int) -> HttpResponse:
    """El comprobante listo para imprimir: en hoja A4 o en tíquet de 80 mm.

    Es la representación impresa del documento electrónico (el RIDE): lo que se le
    entrega al cliente. El formato lo elige ``?formato=a4`` (por omisión) o
    ``?formato=t80``.
    """
    factura = get_object_or_404(
        Factura.objects.select_related("receptor", "comprobante"), pk=pk
    )
    registro = factura.comprobante if factura.comprobante_id else None

    formato = request.GET.get("formato") or "a4"
    if formato not in FORMATOS_RIDE:
        formato = "a4"

    emisor = conf.configuracion_activa()
    numero = (
        f"{registro.estab}-{registro.pto_emi}-{registro.secuencial}" if registro else ""
    )

    contexto = {
        **marco(request),
        "factura": factura,
        "registro": registro,
        "numero": numero,
        "detalles": factura.detalles.all(),
        "totales": totales_de(factura),
        "subtotales": subtotales_por_tarifa(factura.detalles.all()),
        "iva_por_tarifa": iva_por_tarifa(factura.detalles.all()),
        "informacion_adicional": informacion_adicional_de(factura),
        "formato": formato,
        "es_ticket": formato == "t80",
        "hoja": FORMATOS_RIDE[formato],
        # Se pidió imprimir desde el diálogo: la hoja se imprime sola al abrirse.
        "imprimir_ya": bool(request.GET.get("imprimir")),
        "logo": LogoEmisor.de(emisor),
        "barras": codigo_de_barras(registro.clave_acceso if registro else ""),
        "clave_por_partes": clave_por_partes(registro.clave_acceso if registro else ""),
    }
    return render(request, "facturacion/ride.html", contexto)


@login_required
@require_POST
@requiere_lectura("facturas")
def accion(request: HttpRequest, pk: int, que: str) -> HttpResponse:
    """Reintentar el envío, consultar al SRI o rehacer la fecha del comprobante."""
    factura = get_object_or_404(Factura, pk=pk)
    registro = factura.comprobante if factura.comprobante_id else None
    if registro is None:
        messages.error(request, "Esta factura todavía no se ha emitido.")
        return redirect("facturacion:factura", pk=pk)

    if que != "consultar":
        exigir_escritura(request, "facturas")

    try:
        if que == "reintentar":
            # Reutiliza el XML ya registrado; si el SRI lo había devuelto, el
            # paquete lo rehace con un secuencial nuevo (el devuelto queda quemado).
            registro = facturacion.reintentar(factura, encolar=False) or registro
            registro.refresh_from_db()
            messages.info(request, f"Reintento hecho: {ESTADOS.get(registro.estado, registro.estado)}.")
        elif que == "consultar":
            # Pregunta al SRI por la clave, por si autorizó después de enviarse.
            services.autorizar(registro)
            registro.refresh_from_db()
            messages.info(request, f"El SRI responde: {ESTADOS.get(registro.estado, registro.estado)}.")
        elif que == "fecha":
            services.actualizar_fecha(registro)
            messages.success(request, "Comprobante refechado al día de hoy (la clave cambió).")
        else:
            messages.error(request, "Esa acción no existe.")
    except Exception as exc:  # noqa: BLE001 - se le cuenta al usuario, tal cual
        messages.error(request, f"No se pudo: {type(exc).__name__}: {exc}")
    return redirect("facturacion:factura", pk=pk)


@login_required
@requiere_lectura("facturas")
def xml(request: HttpRequest, pk: int, cual: str = "autorizado") -> HttpResponse:
    """Un documento del comprobante: el XML, la respuesta del SRI o el error.

    Se sirve lo guardado en la base (no del disco), para poder mirarlo o guardarlo
    aunque los archivos no se conserven. Con ``?descargar=1`` baja como archivo; sin
    él, se abre en el navegador.
    """
    factura = get_object_or_404(Factura, pk=pk)
    registro = factura.comprobante if factura.comprobante_id else None
    documento = DOCUMENTOS_POR_CLAVE.get(cual)
    contenido = ""
    if registro is not None and documento is not None:
        contenido = getattr(registro, documento["campo"], "") or ""

    if not documento or not contenido:
        messages.error(request, f"Todavía no hay «{cual}» en esta factura.")
        return redirect("facturacion:factura", pk=pk)

    respuesta = HttpResponse(contenido, content_type=f"{documento['tipo']}; charset=utf-8")
    nombre = f"{registro.numero_comprobante}_{documento['archivo']}"
    descarga = "attachment" if request.GET.get("descargar") else "inline"
    respuesta["Content-Disposition"] = f'{descarga}; filename="{nombre}"'
    return respuesta


# --------------------------------------------------------------- el catálogo


def _producto_json(datos: Producto) -> dict[str, Any]:
    """Un producto como lo espera la hoja de facturar.

    Son las mismas claves que sirve el admin del paquete (``ProductoAdmin.datos``):
    lo que rellene el formulario del paquete, lo rellena este, y al revés.
    """
    existencia = getattr(datos, "existencia", None)
    hay = existencia.cantidad if existencia is not None else Decimal("0")
    return {
        "pk": datos.pk,
        "descripcion": datos.descripcion,
        "codigo_principal": datos.codigo_principal,
        "codigo_auxiliar": datos.codigo_auxiliar,
        "unidad_medida": datos.unidad_medida,
        "precio_unitario": f"{datos.precio_unitario:.6f}".rstrip("0").rstrip("."),
        "codigo_porcentaje_iva": datos.codigo_porcentaje_iva,
        "datos_adicionales": datos.datos_adicionales,
        "tipo": datos.tipo,
        "es_servicio": datos.es_servicio,
        "existencia": f"{hay:.3f}".rstrip("0").rstrip(".") or "0",
    }


@login_required
def producto(request: HttpRequest, pk: int) -> JsonResponse:
    """Los datos de un producto, para completar la línea sin volver a escribirlos."""
    return JsonResponse(
        _producto_json(get_object_or_404(Producto, pk=pk)),
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
def buscar_productos(request: HttpRequest) -> JsonResponse:
    """El buscador de la hoja: productos y servicios por código o descripción."""
    buscado = (request.GET.get("q") or "").strip()
    productos = Producto.objects.filter(activo=True)
    if buscado:
        productos = productos.filter(
            Q(descripcion__icontains=buscado)
            | Q(codigo_principal__icontains=buscado)
            | Q(codigo_auxiliar__icontains=buscado)
        )
    productos = productos.order_by("descripcion")[:30]
    return JsonResponse(
        {
            "resultados": [_producto_json(datos) for datos in productos],
            "iva": {codigo: str(tasa) for codigo, tasa in PORCENTAJE_IVA.items()},
        },
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
def buscar_clientes(request: HttpRequest) -> JsonResponse:
    """El buscador de la hoja: clientes por razón social o identificación."""
    buscado = (request.GET.get("q") or "").strip()
    clientes = Cliente.objects.all()
    if buscado:
        clientes = clientes.filter(
            Q(razon_social__icontains=buscado) | Q(identificacion__icontains=buscado)
        )
    clientes = clientes.order_by("razon_social")[:30]
    return JsonResponse(
        {
            "resultados": [
                {
                    "pk": datos.pk,
                    "razon_social": datos.razon_social,
                    "identificacion": datos.identificacion,
                    "direccion": datos.direccion,
                    "email": datos.email,
                }
                for datos in clientes
            ]
        },
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
@require_POST
def cliente_nuevo(request: HttpRequest) -> HttpResponse:
    """Crea un cliente desde la misma pantalla, sin irse al admin.

    Facturar a alguien nuevo pasa todos los días: pedirle al usuario que cambie de
    pestaña en mitad de la factura es la clase de detalle que hace que la gente
    vuelva a Excel.
    """
    datos = {
        "razon_social": (request.POST.get("razon_social") or "").strip(),
        "identificacion": (request.POST.get("identificacion") or "").strip(),
        "tipo_identificacion": request.POST.get("tipo_identificacion") or "04",
        "direccion": (request.POST.get("direccion") or "").strip(),
        "email": (request.POST.get("email") or "").strip(),
        "telefono": (request.POST.get("telefono") or "").strip(),
    }
    if not datos["razon_social"] or not datos["identificacion"]:
        messages.error(request, "El cliente necesita razón social e identificación.")
        return redirect("facturar")

    cliente, creado = Cliente.objects.get_or_create(
        identificacion=datos["identificacion"], defaults=datos
    )
    if creado:
        messages.success(request, f"Cliente «{cliente.razon_social}» creado.")
    else:
        messages.info(request, f"«{cliente.razon_social}» ya estaba en el catálogo.")
    return redirect(f"{request.POST.get('volver_a') or '/'}?cliente={cliente.pk}")
