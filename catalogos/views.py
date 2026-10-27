"""Las pantallas del catálogo: productos, servicios y clientes.

El catálogo es la base de todo lo demás: de aquí salen las líneas de la factura y
las existencias del inventario.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any, Optional

import requests
from django.contrib import messages
from django.core.cache import cache
from django.contrib.auth.decorators import login_required
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from factec.catalogos import TipoIdentificacion
from factec.django.documentos import (
    Cliente,
    Conductor,
    FacturaDetalle,
    GuiaRemision,
    Producto,
    TipoProducto,
    Vehiculo,
)
from sri_consultas import consultar_ruc_sri

from facturero.marco import marco
from facturero.precios import precio_con_iva
from personalize_options.decoradores import (
    exigir_escritura,
    exigir_lectura,
    requiere_escritura,
    requiere_lectura,
)
from tienda.models import ProductoTienda

from .sri_datos import direccion_matriz

from .forms import (
    FormularioCliente,
    FormularioConductor,
    FormularioProducto,
    FormularioTienda,
    FormularioVehiculo,
    FormsetImagenes,
)

__all__ = [
    "productos",
    "producto",
    "cliente",
    "clientes",
    "cliente_nuevo",
    "consultar_identificacion",
    "identificar_cliente",
    "conductor",
    "conductores",
    "vehiculo",
    "vehiculos",
]


# --------------------------------------------------------------- productos


@login_required
@requiere_lectura("productos")
def productos(request: HttpRequest) -> HttpResponse:
    """Bienes y servicios, con lo que hay de cada uno."""
    # Cuántas veces se ha facturado cada uno: el paquete no deja la relación inversa
    # desde el producto, así que se cuenta sobre las líneas.
    lineas = (
        FacturaDetalle.objects.filter(producto=OuterRef("pk"))
        .values("producto")
        .annotate(cuantas=Count("pk"))
        .values("cuantas")
    )
    lista = Producto.objects.select_related("productotienda").annotate(
        cuantas_veces=Coalesce(Subquery(lineas, output_field=IntegerField()), 0)
    ).order_by("descripcion")

    tipo = request.GET.get("tipo") or ""
    estado = request.GET.get("estado") or ""
    texto = (request.GET.get("q") or "").strip()

    if tipo:
        lista = lista.filter(tipo=tipo)
    if estado == "activos":
        lista = lista.filter(activo=True)
    elif estado == "inactivos":
        lista = lista.filter(activo=False)
    if texto:
        lista = lista.filter(
            Q(descripcion__icontains=texto)
            | Q(codigo_principal__icontains=texto)
            | Q(codigo_auxiliar__icontains=texto)
        )

    # El precio guardado es sin IVA: la lista enseña también lo que paga el cliente.
    productos = list(lista)
    for producto in productos:
        producto.precio_con_iva = precio_con_iva(producto)
        producto.tienda = getattr(producto, "productotienda", None)

    contexto = {
        **marco(request),
        "productos": productos,
        "filtros": {"tipo": tipo, "estado": estado, "q": texto},
        "tipos": TipoProducto.choices,
        "cuantos": len(productos),
        "cuantos_servicios": Producto.objects.filter(tipo=TipoProducto.SERVICIO.value).count(),
        "cuantos_bienes": Producto.objects.filter(tipo=TipoProducto.PRODUCTO.value).count(),
    }
    return render(request, "catalogos/productos.html", contexto)


@login_required
@requiere_lectura("productos")
def producto(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Crear o corregir un producto o servicio, con su parte de tienda.

    La tienda es la misma ficha del producto, no otra alta: si se deja todo vacío, el
    producto se queda fuera del catálogo web; en cuanto se marca «publicado» o se
    escribe algo, se guarda su extensión con los mismos datos fiscales.
    """
    from inventario.models import Existencia, Movimiento, TipoMovimiento

    objeto = get_object_or_404(Producto, pk=pk) if pk else Producto()
    existencia = Existencia.objects.filter(producto=objeto).first() if objeto.pk else None
    tienda = ProductoTienda.de(objeto)

    if request.method == "POST":
        exigir_escritura(request, "productos")
        formulario = FormularioProducto(request.POST, instance=objeto)
        formulario_tienda = None
        formset_imagenes = None
        if formulario.is_valid():
            # La tienda se valida antes de guardar nada: si la oferta o las fechas
            # están mal, el producto no se queda a medias.
            extension = tienda or ProductoTienda()
            _copiar_del_formulario(extension, formulario.cleaned_data)
            formulario_tienda = FormularioTienda(
                request.POST, request.FILES, instance=extension
            )
            if formulario_tienda.is_valid():
                guardado = formulario.save()
                minimo = formulario.cleaned_data.get("minimo") or Decimal("0")
                ubicacion = formulario.cleaned_data.get("ubicacion") or ""
                if guardado.es_producto:
                    existencia, _ = Existencia.objects.get_or_create(producto=guardado)
                    existencia.minimo = minimo
                    existencia.ubicacion = ubicacion
                    existencia.save()

                    inicial = formulario.cleaned_data.get("stock_inicial")
                    if inicial and not Movimiento.objects.filter(producto=guardado).exists():
                        Movimiento.objects.create(
                            producto=guardado,
                            fecha=guardado.creado.date() if guardado.creado else None,
                            tipo=TipoMovimiento.ENTRADA.value,
                            cantidad=inicial,
                            motivo="Inventario inicial",
                            usuario=request.user,
                        )

                tienda = _guardar_la_tienda(
                    guardado, formulario_tienda, hay_fotos=_trae_archivos(request)
                )
                formset_imagenes = FormsetImagenes(
                    _sin_fotos_vacias(request.POST, request.FILES),
                    request.FILES,
                    instance=tienda or ProductoTienda(),
                )
                # Si la petición no trae el formset (por ejemplo, la API o una
                # prueba), se guarda sin tocar las fotos.
                trae_fotos = f"{formset_imagenes.prefix}-TOTAL_FORMS" in request.POST
                if not trae_fotos or formset_imagenes.is_valid():
                    if trae_fotos:
                        formset_imagenes.save()
                    if pk:
                        messages.success(request, "Cambios guardados.")
                    else:
                        messages.success(
                            request, f"«{guardado.descripcion}» está en el catálogo."
                        )
                    return redirect("catalogos:productos")
                # Las fotos no se pudieron guardar, pero el producto sí: se sigue en
                # su pantalla, con las fotos marcadas, para corregirlas sin darlo de
                # alta otra vez. Con una redirección el error se perdía y solo se veía
                # el aviso, sin decir cuál era la foto.
                messages.error(request, "El producto se guardó; revise las fotos de la tienda.")
                objeto = guardado
                pk = guardado.pk
                tienda = tienda or ProductoTienda.de(guardado)
                existencia = (
                    Existencia.objects.filter(producto=guardado).first()
                    if guardado.es_producto
                    else None
                )
            messages.error(request, "Revise lo que está marcado en rojo en la tienda.")
        else:
            messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioProducto(instance=objeto)
        formulario_tienda = FormularioTienda(instance=tienda or ProductoTienda())
        _heredar_del_producto(formulario_tienda.instance, objeto)
        formset_imagenes = FormsetImagenes(instance=tienda or ProductoTienda())

    contexto = {
        **marco(request),
        "formulario": formulario,
        "formulario_tienda": formulario_tienda,
        "formset_imagenes": formset_imagenes,
        "producto": objeto,
        "tienda": tienda,
        "existencia": existencia,
        "es_nuevo": objeto.pk is None,
    }
    return render(request, "catalogos/producto.html", contexto)


def _heredar_del_producto(destino: ProductoTienda, origen: Producto) -> None:
    """Copia los campos del producto fiscal en la extensión, para validar y guardar.

    ``ProductoTienda`` hereda el producto; cuando todavía no se ha guardado, los
    campos heredados están vacíos y la validación de la oferta no sabría contra qué
    precio comparar.
    """
    for campo in Producto._meta.concrete_fields:
        setattr(destino, campo.attname, getattr(origen, campo.attname))


def _copiar_del_formulario(destino: ProductoTienda, datos: dict) -> None:
    """Igual que :func:`_heredar_del_producto`, pero con lo que trae el formulario.

    Se usa antes de guardar: la oferta se valida contra el precio que se acaba de
    escribir, no contra el que había en la base.
    """
    for campo in Producto._meta.concrete_fields:
        if campo.attname in datos:
            setattr(destino, campo.attname, datos[campo.attname])


def _sin_fotos_vacias(post: Any, archivos: Any) -> Any:
    """Marca para borrar las filas del formset que no son ninguna foto.

    El navegador puede dejar puestos el orden o el texto alternativo de una fila
    a la que al final no se le eligió archivo. Sin archivo ni foto guardada no es
    una foto, pero Django la mira como una foto a la que le falta la imagen y da
    el formset por malo, aunque el producto se haya guardado bien. Se descarta
    aquí, que es donde se sabe si vino el archivo.
    """
    prefijo = FormsetImagenes.get_default_prefix()
    try:
        total = int(post.get(f"{prefijo}-TOTAL_FORMS") or 0)
    except (TypeError, ValueError):
        return post
    limpio = post.copy()
    for indice in range(total):
        hay_archivo = bool(archivos.get(f"{prefijo}-{indice}-imagen"))
        hay_foto = bool((post.get(f"{prefijo}-{indice}-id") or "").strip())
        if not hay_archivo and not hay_foto:
            limpio[f"{prefijo}-{indice}-DELETE"] = "on"
    return limpio


def _trae_archivos(request: HttpRequest) -> bool:
    """¿La petición sube alguna foto? Basta con que venga un archivo del formset."""
    prefijo = f"{FormsetImagenes.get_default_prefix()}-"
    return any(clave.startswith(prefijo) for clave in request.FILES)


def _guardar_la_tienda(
    producto_guardado: Producto, formulario: FormularioTienda, hay_fotos: bool = False
) -> Optional[ProductoTienda]:
    """Guarda la parte de tienda si se tocó; si no, la deja como estaba.

    Una foto sola ya es motivo para extender el producto: si no, se subiría y se
    perdería al guardar.
    """
    if not formulario.tiene_datos and not hay_fotos:
        return ProductoTienda.de(producto_guardado)
    tienda = ProductoTienda.extender(producto_guardado)
    for nombre, valor in formulario.cleaned_data.items():
        setattr(tienda, nombre, valor)
    tienda.save()
    return tienda


# ----------------------------------------------------------------- clientes


@login_required
@requiere_lectura("clientes")
def clientes(request: HttpRequest) -> HttpResponse:
    """Quién compra, con lo que se le ha facturado."""
    lista = Cliente.objects.annotate(
        cuantas_facturas=Count("facturas", distinct=True)
    ).order_by("razon_social")

    texto = (request.GET.get("q") or "").strip()
    if texto:
        lista = lista.filter(
            Q(razon_social__icontains=texto)
            | Q(identificacion__icontains=texto)
            | Q(email__icontains=texto)
            | Q(direccion__icontains=texto)
        )

    contexto = {
        **marco(request),
        "clientes": lista,
        "filtros": {"q": texto},
        "cuantos": lista.count(),
    }
    return render(request, "catalogos/clientes.html", contexto)


def _json_cliente(
    cliente: Any,
    identificacion: str,
    origen: str,
    mensaje: str,
    sri: Any = None,
    tipo: str = "",
    nuevo: bool = False,
) -> JsonResponse:
    """La ficha del cliente tal como la espera la pantalla de facturación."""
    if not tipo:
        tipo = cliente.tipo_identificacion
        if not tipo:
            if len(identificacion) == 10:
                tipo = TipoIdentificacion.CEDULA.value
            elif len(identificacion) == 13:
                tipo = TipoIdentificacion.RUC.value
    datos = {
        "pk": cliente.pk,
        "razon_social": cliente.razon_social,
        "identificacion": identificacion,
        "tipo_identificacion": tipo,
        "direccion": cliente.direccion,
        "email": cliente.email,
        "telefono": cliente.telefono,
    }
    respuesta = {
        "encontrado": True,
        "origen": origen,
        # Solo se avisa en pantalla cuando hay un cliente nuevo: si ya estaba
        # guardado, sus datos se cargan sin decir nada.
        "nuevo": bool(nuevo),
        "mensaje": mensaje,
        "cliente": datos,
    }
    if sri is not None:
        respuesta["sri"] = sri
    return JsonResponse(respuesta, json_dumps_params={"ensure_ascii": False})


def _campos_sri(resultado: Any) -> dict[str, Any]:
    """Los datos del contribuyente con los nombres que usa la interfaz."""
    crudo = getattr(resultado, "crudo", None) or {}
    planos = getattr(resultado, "datos", None) or {}

    def dato(*claves: str) -> str:
        for clave in claves:
            valor = crudo.get(clave)
            if valor not in (None, ""):
                return str(valor).strip()
        return ""

    return {
        "ruc": getattr(resultado, "ruc", ""),
        "razon_social": dato("razonSocial") or planos.get("Razón social", ""),
        "estado": dato("estadoContribuyenteRuc"),
        "tipo_contribuyente": dato("tipoContribuyente"),
        "regimen": dato("regimen") or dato("categoria"),
        "categoria": dato("categoria"),
        "actividad_economica": dato("actividadEconomicaPrincipal"),
        "obligado_contabilidad": dato("obligadoLlevarContabilidad"),
        "agente_retencion": dato("agenteRetencion"),
        "contribuyente_especial": dato("contribuyenteEspecial"),
        "contribuyente_fantasma": dato("contribuyenteFantasma"),
        "transacciones_inexistentes": dato("transaccionesInexistente"),
        "motivo_cancelacion": dato("motivoCancelacionSuspension"),
        "fechas": crudo.get("informacionFechasContribuyente") or {},
        "representantes_legales": crudo.get("representantesLegales"),
    }


@login_required
@require_POST
@requiere_lectura("clientes")
def identificar_cliente(request: HttpRequest) -> JsonResponse:
    """Busca por cédula, RUC, pasaporte u otro documento.

    Si está en el catálogo se devuelve tal cual. Para cédula y RUC, si no está y
    el SRI lo conoce, se crea con los datos del catastro. Para pasaporte,
    consumidor final o identificación del exterior no hay consulta al SRI: se
    busca en el catálogo y, si no está, se piden los datos a mano.
    """
    pedido = (request.POST.get("tipo_identificacion") or "auto").strip()
    texto = (request.POST.get("identificacion") or "").strip().upper()
    tipos = {
        TipoIdentificacion.RUC.value,
        TipoIdentificacion.CEDULA.value,
        TipoIdentificacion.PASAPORTE.value,
        TipoIdentificacion.CONSUMIDOR_FINAL.value,
        TipoIdentificacion.IDENTIFICACION_EXTERIOR.value,
    }
    if pedido not in tipos:
        pedido = "auto"

    # Cédula, RUC y consumidor final son numéricos; el pasaporte y la
    # identificación del exterior pueden llevar letras.
    numerico = pedido in {
        "auto",
        TipoIdentificacion.RUC.value,
        TipoIdentificacion.CEDULA.value,
        TipoIdentificacion.CONSUMIDOR_FINAL.value,
    }
    numero = re.sub(r"\D", "", texto) if numerico else re.sub(r"\s+", "", texto)

    if pedido == "auto":
        if len(numero) == 10:
            tipo = TipoIdentificacion.CEDULA.value
        elif len(numero) == 13:
            tipo = TipoIdentificacion.RUC.value
        else:
            return JsonResponse(
                {
                    "encontrado": False,
                    "pedir_datos": False,
                    "mensaje": (
                        "Si es pasaporte u otro documento, elija primero el tipo "
                        "de documento."
                    ),
                },
                json_dumps_params={"ensure_ascii": False},
            )
    else:
        tipo = pedido

    if tipo == TipoIdentificacion.RUC.value and not (
        len(numero) == 13 and numero.isdigit()
    ):
        return JsonResponse(
            {
                "encontrado": False,
                "pedir_datos": False,
                "mensaje": "El RUC debe tener 13 dígitos.",
            },
            json_dumps_params={"ensure_ascii": False},
        )
    if tipo == TipoIdentificacion.CEDULA.value and not (
        len(numero) == 10 and numero.isdigit()
    ):
        return JsonResponse(
            {
                "encontrado": False,
                "pedir_datos": False,
                "mensaje": "La cédula debe tener 10 dígitos.",
            },
            json_dumps_params={"ensure_ascii": False},
        )
    if tipo in {
        TipoIdentificacion.PASAPORTE.value,
        TipoIdentificacion.IDENTIFICACION_EXTERIOR.value,
    } and len(numero) < 3:
        return JsonResponse(
            {
                "encontrado": False,
                "pedir_datos": False,
                "mensaje": "Escriba el número del documento.",
            },
            json_dumps_params={"ensure_ascii": False},
        )

    identificacion = numero
    local = Cliente.objects.filter(identificacion=identificacion).first()
    if local is not None and local.tipo_identificacion not in ("", tipo):
        # El mismo número puede ser otra cosa (por ejemplo, un pasaporte que
        # coincide con una cédula): no se mezclan fichas de distinto tipo.
        local = None
    if local is not None:
        return _json_cliente(
            local,
            identificacion,
            "local",
            "Ya está en el catálogo; se usan sus datos guardados.",
            tipo=local.tipo_identificacion or tipo,
        )

    if tipo not in {
        TipoIdentificacion.RUC.value,
        TipoIdentificacion.CEDULA.value,
    }:
        return JsonResponse(
            {
                "encontrado": False,
                "pedir_datos": True,
                "mensaje": (
                    "No está en el catálogo. Complete la razón social y los demás "
                    "datos del cliente."
                ),
            },
            json_dumps_params={"ensure_ascii": False},
        )

    es_cedula = tipo == TipoIdentificacion.CEDULA.value
    ruc_consulta = f"{numero}001" if es_cedula else numero
    try:
        resultado = consultar_ruc_sri(ruc_consulta, timeout=8.0)
        direccion = direccion_matriz(ruc_consulta) if resultado.encontrado else ""
    except (requests.RequestException, ValueError):
        logging.getLogger(__name__).warning(
            "No se pudo consultar la identificación %s en el SRI",
            ruc_consulta,
            exc_info=True,
        )
        return JsonResponse(
            {
                "encontrado": False,
                "pedir_datos": False,
                "mensaje": (
                    "El SRI no respondió en este momento. Vuelva a intentarlo o use "
                    "«Completar los datos a mano»."
                ),
            },
            json_dumps_params={"ensure_ascii": False},
        )

    if not resultado.encontrado:
        que = "esa cédula" if es_cedula else "ese RUC"
        return JsonResponse(
            {
                "encontrado": False,
                "pedir_datos": True,
                "mensaje": (
                    f"El SRI no devolvió datos para {que}. Complete la razón social "
                    "y los demás datos del cliente."
                ),
            },
            json_dumps_params={"ensure_ascii": False},
        )

    campos = _campos_sri(resultado)
    identificacion = numero
    cliente, creado = Cliente.objects.get_or_create(
        identificacion=identificacion,
        defaults={
            "razon_social": campos["razon_social"] or identificacion,
            "tipo_identificacion": tipo,
            "direccion": direccion,
            "email": "",
            "telefono": "",
        },
    )
    mensaje = (
        "Cliente agregado al catálogo con los datos del SRI."
        if creado
        else "Ya estaba en el catálogo; se usan sus datos guardados."
    )
    return _json_cliente(cliente, identificacion, "sri", mensaje, sri=campos, tipo=tipo, nuevo=creado)


@login_required
@requiere_lectura("clientes")
def consultar_identificacion(request: HttpRequest) -> JsonResponse:
    """Datos de un cliente por RUC: primero la base local y, si es nuevo, el SRI.

    El catastro público del SRI se consulta **solo** cuando la identificación no
    está en el catálogo. Así el alta de un cliente nuevo se completa sola, pero
    el día a día no depende de la red ni castiga al SRI con la misma consulta.
    """
    pedido = (request.GET.get("cliente") or "").strip()
    if pedido.isdigit():
        local = Cliente.objects.filter(pk=int(pedido)).first()
        if local is not None:
            return _json_cliente(
                local,
                local.identificacion,
                "local",
                "Ya está en el catálogo; se usan sus datos guardados.",
                tipo=local.tipo_identificacion,
            )

    numero = re.sub(r"\D", "", request.GET.get("identificacion") or "")
    if not numero:
        return JsonResponse(
            {"encontrado": False, "mensaje": "Escriba el RUC o la cédula."},
            json_dumps_params={"ensure_ascii": False},
        )

    local = Cliente.objects.filter(identificacion=numero).first()
    if local is not None:
        return _json_cliente(
            local,
            numero,
            "local",
            "Ya está en el catálogo; se usan sus datos guardados.",
            tipo=local.tipo_identificacion,
        )

    if len(numero) not in (10, 13):
        return JsonResponse(
            {
                "encontrado": False,
                "mensaje": "Escriba un RUC de 13 dígitos o una cédula de 10.",
            },
            json_dumps_params={"ensure_ascii": False},
        )

    es_cedula = len(numero) == 10
    ruc_consulta = f"{numero}001" if es_cedula else numero
    llave = f"consulta_sri:{ruc_consulta}"
    guardado = cache.get(llave)
    try:
        if guardado is None:
            datos = consultar_ruc_sri(ruc_consulta, timeout=8.0)
            direccion = direccion_matriz(ruc_consulta) if datos.encontrado else ""
            if datos.encontrado:
                cache.set(llave, (datos, direccion), 3600)
        else:
            datos, direccion = guardado
    except (requests.RequestException, ValueError):
        logging.getLogger(__name__).warning(
            "No se pudo consultar el RUC %s en el SRI", ruc_consulta, exc_info=True
        )
        return JsonResponse(
            {
                "encontrado": False,
                "mensaje": (
                    "El SRI no respondió en este momento. Escriba los datos a mano "
                    "o vuelva a intentarlo más tarde."
                ),
            },
            json_dumps_params={"ensure_ascii": False},
        )

    if not datos.encontrado:
        que = "esa cédula" if es_cedula else "ese RUC"
        return JsonResponse(
            {
                "encontrado": False,
                "mensaje": (
                    f"El SRI no devolvió datos para {que}. "
                    "Revise el número o escriba los datos a mano."
                ),
            },
            json_dumps_params={"ensure_ascii": False},
        )

    crudo = getattr(datos, "crudo", None) or {}
    datos_planos = getattr(datos, "datos", None) or {}

    def dato(*claves: str) -> str:
        """El primer valor que traiga el SRI, con su nombre original."""
        for clave in claves:
            valor = crudo.get(clave)
            if valor not in (None, ""):
                return str(valor)
        return ""

    razon_social = dato("razonSocial") or datos_planos.get("Razón social", "")
    mensaje = "Datos traídos del catastro del SRI."
    if direccion:
        mensaje += " Se cargó la dirección matriz; complete correo y teléfono."
    else:
        mensaje += " Complete dirección, correo y teléfono."

    return JsonResponse(
        {
            "encontrado": True,
            "origen": "sri",
            "mensaje": mensaje,
            "cliente": {
                "razon_social": razon_social,
                "identificacion": numero if es_cedula else (datos.ruc or numero),
                "tipo_identificacion": (
                    TipoIdentificacion.CEDULA.value
                    if es_cedula
                    else TipoIdentificacion.RUC.value
                ),
                "direccion": direccion,
                "email": "",
                "telefono": "",
            },
            "sri": {
                "ruc": datos.ruc,
                "razon_social": razon_social,
                "estado": dato("estadoContribuyenteRuc"),
                "tipo_contribuyente": dato("tipoContribuyente"),
                "regimen": dato("regimen") or dato("categoria"),
                "categoria": dato("categoria"),
                "actividad_economica": dato("actividadEconomicaPrincipal"),
                "obligado_contabilidad": dato("obligadoLlevarContabilidad"),
                "agente_retencion": dato("agenteRetencion"),
                "contribuyente_especial": dato("contribuyenteEspecial"),
                "contribuyente_fantasma": dato("contribuyenteFantasma"),
                "transacciones_inexistentes": dato("transaccionesInexistente"),
                "motivo_cancelacion": dato("motivoCancelacionSuspension"),
                "fechas": crudo.get("informacionFechasContribuyente") or {},
                "representantes_legales": crudo.get("representantesLegales"),
                "datos": datos_planos,
                "crudo": crudo.to_dict() if hasattr(crudo, "to_dict") else crudo,
            },
        },
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
@requiere_lectura("clientes")
def cliente(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Crear o corregir un cliente."""
    objeto = get_object_or_404(Cliente, pk=pk) if pk else Cliente()
    if request.method == "POST":
        exigir_escritura(request, "clientes")
        formulario = FormularioCliente(request.POST, instance=objeto)
        if formulario.is_valid():
            guardado = formulario.save()
            messages.success(request, f"«{guardado.razon_social}» guardado.")
            return redirect("catalogos:clientes")
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioCliente(instance=objeto)

    contexto = {
        **marco(request),
        "formulario": formulario,
        "cliente": objeto,
        "es_nuevo": pk is None,
        "facturas": objeto.facturas.all()[:10] if objeto.pk else [],
    }
    return render(request, "catalogos/cliente.html", contexto)


@login_required
@require_POST
@requiere_escritura("clientes")
def cliente_nuevo(request: HttpRequest) -> HttpResponse:
    """Crea un cliente desde la misma pantalla de facturación.

    Facturar a alguien nuevo pasa todos los días: obligar a cambiar de pantalla a
    mitad de la factura es la clase de detalle que hace que la gente vuelva a Excel.
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
        return redirect(request.POST.get("volver_a") or "facturacion:facturar")

    cliente, es_nuevo = Cliente.objects.get_or_create(
        identificacion=datos["identificacion"], defaults=datos
    )
    if es_nuevo:
        messages.success(request, f"Cliente «{cliente.razon_social}» añadido al catálogo.")
    else:
        messages.info(request, f"«{cliente.razon_social}» ya estaba en el catálogo.")
    return redirect(f"{request.POST.get('volver_a') or '/'}?cliente={cliente.pk}")


# ------------------------------------------------------- transporte (guías)


def _guias_por(campo_guia: str, campo_lista: str) -> Any:
    """Cuenta las guías que usan un valor de este catálogo.

    La guía guarda del transportista su RUC y del vehículo su placa (así viaja al
    SRI), no una relación: se cuentan cotejando esos campos, igual que hace el
    formulario de la guía para dejarlos elegidos. El ``order_by()`` vacío evita que
    el orden por omisión del comprobante entre en la cuenta.
    """
    return (
        GuiaRemision.objects.filter(**{campo_guia: OuterRef(campo_lista)})
        .order_by()
        .values(campo_guia)
        .annotate(cuantas=Count("pk"))
        .values("cuantas")
    )


@login_required
@requiere_lectura("conductores")
def conductores(request: HttpRequest) -> HttpResponse:
    """Los transportistas y choferes que se eligen al hacer una guía."""
    lista = Conductor.objects.annotate(
        cuantas_guias=Coalesce(
            Subquery(_guias_por("ruc_transportista", "identificacion"),
                     output_field=IntegerField()),
            0,
        )
    ).order_by("razon_social")

    texto = (request.GET.get("q") or "").strip()
    if texto:
        lista = lista.filter(
            Q(razon_social__icontains=texto)
            | Q(identificacion__icontains=texto)
            | Q(telefono__icontains=texto)
        )

    contexto = {
        **marco(request),
        "conductores": lista,
        "filtros": {"q": texto},
        "cuantos": lista.count(),
        "cuantos_activos": Conductor.objects.filter(activo=True).count(),
    }
    return render(request, "catalogos/conductores.html", contexto)


@login_required
@requiere_lectura("conductores")
def conductor(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Dar de alta o corregir un transportista."""
    objeto = get_object_or_404(Conductor, pk=pk) if pk else Conductor()
    if request.method == "POST":
        exigir_escritura(request, "conductores")
        formulario = FormularioConductor(request.POST, instance=objeto)
        if formulario.is_valid():
            guardado = formulario.save()
            messages.success(request, f"«{guardado.razon_social}» guardado.")
            return redirect("catalogos:conductores")
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioConductor(instance=objeto)

    contexto = {
        **marco(request),
        "formulario": formulario,
        "conductor": objeto,
        "es_nuevo": pk is None,
    }
    return render(request, "catalogos/conductor.html", contexto)


@login_required
@requiere_lectura("vehiculos")
def vehiculos(request: HttpRequest) -> HttpResponse:
    """Los vehículos de los que sale la placa de la guía."""
    lista = Vehiculo.objects.annotate(
        cuantas_guias=Coalesce(
            Subquery(_guias_por("placa", "placa"), output_field=IntegerField()),
            0,
        )
    ).order_by("placa")

    texto = (request.GET.get("q") or "").strip()
    if texto:
        lista = lista.filter(
            Q(placa__icontains=texto) | Q(descripcion__icontains=texto)
        )

    contexto = {
        **marco(request),
        "vehiculos": lista,
        "filtros": {"q": texto},
        "cuantos": lista.count(),
        "cuantos_activos": Vehiculo.objects.filter(activo=True).count(),
    }
    return render(request, "catalogos/vehiculos.html", contexto)


@login_required
@requiere_lectura("vehiculos")
def vehiculo(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Dar de alta o corregir un vehículo."""
    objeto = get_object_or_404(Vehiculo, pk=pk) if pk else Vehiculo()
    if request.method == "POST":
        exigir_escritura(request, "vehiculos")
        formulario = FormularioVehiculo(request.POST, instance=objeto)
        if formulario.is_valid():
            guardado = formulario.save()
            messages.success(request, f"Vehículo «{guardado.placa}» guardado.")
            return redirect("catalogos:vehiculos")
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioVehiculo(instance=objeto)

    contexto = {
        **marco(request),
        "formulario": formulario,
        "vehiculo": objeto,
        "es_nuevo": pk is None,
    }
    return render(request, "catalogos/vehiculo.html", contexto)
