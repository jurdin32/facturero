"""Las pantallas de la tienda: la pública y la de los pedidos.

La tienda pública no pide sesión: enseña lo publicado, arma el carrito en la sesión
y deja un pedido. La pantalla de pedidos es de la aplicación, con su permiso: desde
ahí se revisa cada pedido y se arma la factura para emitirla en «Facturar».
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.formats import number_format
from django.db.models import Count, Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from factec.django import conf
from factec.django.models import EstadoComprobante
from factec.modelos import cuantizar
from personalize_options.decoradores import (
    exigir_escritura,
    requiere_lectura,
)

from facturero.marco import marco

from .carrito import Carrito, LineaDelCarrito
from .forms import (
    FormularioCategoria,
    FormularioPedido,
    FormularioPregunta,
    FormularioResena,
)
from .models import Categoria, Pedido, Pregunta, ProductoTienda, Resena
from .servicios import crear_pedido, factura_del_pedido

__all__ = [
    "enlace_viejo",
    "portada",
    "categoria",
    "producto",
    "carrito",
    "agregar",
    "actualizar_carrito",
    "linea_carrito",
    "buscar",
    "ofertas",
    "confirmar",
    "gracias",
    "pedidos",
    "pedido",
    "facturar",
    "anular",
    "categorias",
    "categoria_form",
    "preguntar",
    "resenar",
    "seguimiento",
    "preguntas",
    "responder_pregunta",
    "publicar_pregunta",
    "resenas",
    "moderar_resena",
]


# ------------------------------------------------------------------ la tienda


#: Lo que se administra, que ahora vive en la trastienda.
DE_LA_TRASTIENDA = ("categorias", "pedidos", "preguntas", "resenas")


def enlace_viejo(request: HttpRequest, resto: str = "") -> HttpResponse:
    """Las direcciones de antes —``/tienda/...``— llevan a donde están ahora.

    La tienda se mudó a la raíz del dominio para que cualquiera pueda entrar sin
    escribir una dirección rara. Los enlaces que ya se habían repartido se quedan
    con la de antes, y esto los manda a su sitio en vez de dar un 404.
    """
    primero = resto.split("/")[0]
    destino = "/" + resto
    if primero in DE_LA_TRASTIENDA:
        destino = "/wadmin/tienda/" + resto
    return redirect(destino, permanent=True)


def portada(request: HttpRequest) -> HttpResponse:
    """Lo que se ve al entrar: las ofertas, los destacados y las categorías."""
    publicados = list(
        ProductoTienda.objects.publicadas()
        .select_related("categoria")
        .prefetch_related("imagenes")
    )
    ofertas = [producto for producto in publicados if producto.oferta_vigente][:6]
    destacados = [producto for producto in publicados if producto.destacado][:8]
    son_destacados = bool(destacados)
    if not destacados:
        destacados = publicados[:8]

    vendidos = (
        ProductoTienda.objects.publicadas()
        .annotate(ventas=Sum("lineas_de_pedido__cantidad"))
        .filter(ventas__gt=0)
        .select_related("categoria")
        .prefetch_related("imagenes")
        .order_by("-ventas")[:6]
    )

    # El slider de la portada: primero lo destacado, y si no hay bastante, el
    # resto del catálogo. Solo entran los que tienen foto, que es lo que se ve.
    con_foto = [
        producto for producto in destacados + publicados if producto.imagen_principal
    ]
    diapositivas = []
    vistos_en_el_slider = set()
    for producto in con_foto:
        if producto.pk in vistos_en_el_slider:
            continue
        vistos_en_el_slider.add(producto.pk)
        diapositivas.append(producto)
        if len(diapositivas) == 6:
            break

    contexto = {
        **_publico(),
        "categorias": Categoria.objects.filter(activa=True, padre__isnull=True),
        "ofertas": ofertas,
        "destacados": destacados,
        "vendidos": list(vendidos),
        "diapositivas": diapositivas,
        "son_destacados": son_destacados,
        "vistos": _ultimos_vistos(request),
        "total": len(publicados),
    }
    return render(request, "tienda/portada.html", contexto)


def categoria(request: HttpRequest, slug: str) -> HttpResponse:
    """Lo publicado en una categoría o en cualquiera de sus subcategorías."""
    la_categoria = get_object_or_404(Categoria, slug=slug, activa=True)
    productos = (
        ProductoTienda.objects.en_categoria(la_categoria)
        .select_related("categoria")
        .prefetch_related("imagenes")
    )
    return _listado(request, productos, titulo=la_categoria.nombre, categoria=la_categoria)


def buscar(request: HttpRequest) -> HttpResponse:
    """Los resultados de la barra de búsqueda."""
    texto = (request.GET.get("q") or "").strip()
    productos = (
        ProductoTienda.objects.publicadas()
        .select_related("categoria")
        .prefetch_related("imagenes")
    )
    if texto:
        productos = productos.filter(
            Q(titulo__icontains=texto)
            | Q(descripcion__icontains=texto)
            | Q(resumen__icontains=texto)
            | Q(descripcion_larga__icontains=texto)
            | Q(codigo_principal__icontains=texto)
            | Q(codigo_auxiliar__icontains=texto)
        )
    else:
        productos = productos.none()
    titulo = f"Resultados para «{texto}»" if texto else "Buscar en la tienda"
    return _listado(request, productos, titulo=titulo, q=texto)


def ofertas(request: HttpRequest) -> HttpResponse:
    """Lo que tiene una oferta vigente."""
    publicados = (
        ProductoTienda.objects.publicadas()
        .select_related("categoria")
        .prefetch_related("imagenes")
    )
    con_oferta = [producto for producto in publicados if producto.oferta_vigente]
    return _listado(request, con_oferta, titulo="Ofertas")


def producto(request: HttpRequest, slug: str) -> HttpResponse:
    """La ficha de un producto publicado."""
    el_producto = get_object_or_404(
        ProductoTienda.objects.publicadas()
        .select_related("categoria")
        .prefetch_related("imagenes"),
        slug=slug,
    )
    relacionados = (
        ProductoTienda.objects.en_categoria(el_producto.categoria)
        .exclude(pk=el_producto.pk)
        .prefetch_related("imagenes")[:5]
        if el_producto.categoria_id
        else []
    )
    resenas = list(el_producto.resenas.filter(aprobada=True))
    promedio = (
        round(sum(resena.calificacion for resena in resenas) / len(resenas), 1)
        if resenas
        else None
    )
    distribucion = [
        {
            "estrellas": nota,
            "cuantas": len([resena for resena in resenas if resena.calificacion == nota]),
            "porcentaje": round(
                len([resena for resena in resenas if resena.calificacion == nota])
                * 100
                / len(resenas)
            )
            if resenas
            else 0,
        }
        for nota in range(5, 0, -1)
    ]
    preguntas = list(el_producto.preguntas.filter(publicada=True).exclude(respuesta=""))
    _recordar_visto(request, el_producto)
    contexto = {
        **_publico(),
        "producto": el_producto,
        "relacionados": relacionados,
        "resenas": resenas,
        "promedio": promedio,
        "distribucion": distribucion,
        "preguntas": preguntas,
        "formulario_resena": FormularioResena(),
        "notas": list(FormularioResena.PALABRAS.items()),
    }
    return render(request, "tienda/producto.html", contexto)


#: Cuántos productos se guardan de lo que se va mirando.
VISTOS = 8


def _recordar_visto(request: HttpRequest, el_producto: ProductoTienda) -> None:
    """Deja el producto al principio de lo último que se miró, sin repetirlo."""
    vistos = [clave for clave in request.session.get("vistos_tienda", []) if clave != el_producto.pk]
    request.session["vistos_tienda"] = [el_producto.pk, *vistos][:VISTOS]


def _ultimos_vistos(request: HttpRequest) -> List[ProductoTienda]:
    """Los productos que se miraron, en ese orden, de los que siguen publicados."""
    claves = request.session.get("vistos_tienda", [])
    if not claves:
        return []
    encontrados = {
        producto.pk: producto
        for producto in ProductoTienda.objects.publicadas()
        .filter(pk__in=claves)
        .select_related("categoria")
        .prefetch_related("imagenes")
    }
    return [encontrados[clave] for clave in claves if clave in encontrados]


def _listado(
    request: HttpRequest,
    productos: Any,
    *,
    titulo: str,
    categoria: Optional[Categoria] = None,
    q: str = "",
) -> HttpResponse:
    """Pinta un listado con sus filtros, su orden y su paginación.

    Los filtros de precio se aplican sobre el precio con IVA, que es el que se ve;
    por eso se hace aquí y no en la consulta. Con el tamaño de un catálogo de tienda
    no se nota.
    """
    lista = list(productos)
    minimo = _precio_de(request.GET.get("min"))
    maximo = _precio_de(request.GET.get("max"))
    solo_stock = request.GET.get("stock") == "1"
    solo_oferta = request.GET.get("oferta") == "1"
    orden = request.GET.get("orden") or "relevantes"

    filtrados = []
    for producto in lista:
        if solo_stock and not producto.con_stock:
            continue
        if solo_oferta and not producto.oferta_vigente:
            continue
        if minimo is not None and producto.precio < minimo:
            continue
        if maximo is not None and producto.precio > maximo:
            continue
        filtrados.append(producto)

    if orden == "menor":
        filtrados.sort(key=lambda producto: (producto.precio, producto.nombre.lower()))
    elif orden == "mayor":
        filtrados.sort(key=lambda producto: (-producto.precio, producto.nombre.lower()))
    elif orden == "nombre":
        filtrados.sort(key=lambda producto: producto.nombre.lower())

    pagina = Paginator(filtrados, 24).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)

    contexto = {
        **_publico(),
        "titulo": titulo,
        "categoria": categoria,
        "productos": pagina.object_list,
        "pagina": pagina,
        "total": len(filtrados),
        "filtros": {
            "min": request.GET.get("min") or "",
            "max": request.GET.get("max") or "",
            "stock": solo_stock,
            "oferta": solo_oferta,
            "orden": orden,
            "q": q,
        },
        "querystring": parametros.urlencode(),
        "sin_filtros": not (
            minimo is not None
            or maximo is not None
            or solo_stock
            or solo_oferta
        ),
    }
    return render(request, "tienda/listado.html", contexto)


def _precio_de(valor: Optional[str]) -> Optional[Decimal]:
    """Un precio escrito a mano («10,50») o ``None`` si no hay."""
    if not valor or not str(valor).strip():
        return None
    try:
        return cuantizar(Decimal(str(valor).strip().replace(",", ".")))
    except (InvalidOperation, TypeError, ValueError):
        return None


def carrito(request: HttpRequest) -> HttpResponse:
    """Lo que lleva y cuánto suma."""
    el_carrito = Carrito(request)
    contexto = {**_publico(), **_contexto_del_carrito(el_carrito)}
    return render(request, "tienda/carrito.html", contexto)


@require_POST
def agregar(request: HttpRequest) -> HttpResponse:
    """Suma un producto al carrito.

    Vuelve a la ficha si se pidió desde ella (``seguir``), y si no, al carrito: así
    añadir varias cosas no obliga a salir de la ficha.
    """
    el_producto = get_object_or_404(
        ProductoTienda.objects.publicadas(), pk=request.POST.get("producto") or 0
    )
    if not el_producto.con_stock:
        messages.error(request, f"«{el_producto.nombre}» está agotado.")
        return redirect("tienda:producto", slug=el_producto.slug)

    cantidad = _cantidad(request.POST.get("cantidad"))
    if cantidad <= 0:
        messages.error(request, "Escriba una cantidad mayor que cero.")
    else:
        Carrito(request).agregar(el_producto, cantidad)
        if request.POST.get("comprar"):
            return redirect("tienda:confirmar")
        messages.success(request, f"«{el_producto.nombre}» está en el carrito.")

    if request.POST.get("seguir"):
        return redirect("tienda:producto", slug=el_producto.slug)
    return redirect("tienda:carrito")


@require_POST
def actualizar_carrito(request: HttpRequest) -> HttpResponse:
    """Cambia las cantidades o saca una línea del carrito.

    Es la versión sin JavaScript: el carrito de verdad cambia la cantidad en el
    acto, contra :func:`linea_carrito`.
    """
    el_carrito = Carrito(request)
    quitar = request.POST.get("quitar")
    if quitar:
        el_carrito.quitar(quitar)
        messages.info(request, "Se quitó del carrito.")
        return redirect("tienda:carrito")

    productos = ProductoTienda.objects.filter(
        pk__in=_identificadores(request.POST)
    ).in_bulk()
    for identificador, el_producto in productos.items():
        el_carrito.fijar(
            el_producto, _cantidad(request.POST.get(f"cantidad_{identificador}"))
        )
    return redirect("tienda:carrito")


@require_POST
def linea_carrito(request: HttpRequest) -> JsonResponse:
    """Deja una línea en la cantidad pedida y devuelve los totales.

    Lo llama el carrito mientras se escribe, para que el importe cambie sin pulsar
    nada. Con cantidad cero (o menos) la línea sale del carrito. Los importes van ya
    formateados, para que el número se vea igual que el que pinta la plantilla.
    """
    el_carrito = Carrito(request)
    try:
        el_producto = ProductoTienda.objects.publicadas().get(
            pk=int(request.POST.get("producto") or 0)
        )
    except (ProductoTienda.DoesNotExist, TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "Ese producto ya no está en la tienda."}, status=404
        )

    cantidad = _cantidad(request.POST.get("cantidad"))
    quitada = cantidad <= 0
    if quitada:
        el_carrito.quitar(el_producto.pk)
    else:
        if not el_producto.con_stock:
            return JsonResponse(
                {"ok": False, "error": f"«{el_producto.nombre}» está agotado."}, status=409
            )
        el_carrito.fijar(el_producto, cantidad)

    lineas = el_carrito.lineas()
    contexto = _contexto_del_carrito(el_carrito, lineas)
    linea = next((una for una in lineas if una.producto.pk == el_producto.pk), None)
    return JsonResponse(
        {
            "ok": True,
            "quitada": quitada,
            "cantidad": _numero(el_carrito.cantidad_de(el_producto)),
            "linea": number_format(linea.total, 2) if linea else None,
            "subtotal": number_format(contexto["subtotal"], 2),
            "iva": number_format(contexto["iva"], 2),
            "total": number_format(contexto["total"], 2),
            "unidades": _numero(el_carrito.unidades),
            "vacia": not lineas,
        }
    )


def confirmar(request: HttpRequest) -> HttpResponse:
    """Los datos de quien compra y el pedido definitivo."""
    el_carrito = Carrito(request)
    lineas = el_carrito.lineas()
    if not lineas:
        messages.info(request, "El carrito está vacío: elija algo primero.")
        return redirect("tienda:portada")

    if request.method == "POST":
        formulario = FormularioPedido(request.POST)
        if formulario.is_valid():
            try:
                pedido = crear_pedido(el_carrito, formulario.cleaned_data)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                return redirect("tienda:gracias", referencia=pedido.referencia)
    else:
        formulario = FormularioPedido()

    contexto = {
        **_publico(),
        **_contexto_del_carrito(el_carrito, lineas),
        "formulario": formulario,
    }
    return render(request, "tienda/confirmar.html", contexto)


def gracias(request: HttpRequest, referencia: Any) -> HttpResponse:
    """El acuse del pedido, por su referencia (no por el número de la fila)."""
    pedido = get_object_or_404(
        Pedido.objects.select_related("cliente").prefetch_related("lineas"), referencia=referencia
    )
    return render(request, "tienda/gracias.html", {**_publico(), "pedido": pedido})


@require_POST
def preguntar(request: HttpRequest, slug: str) -> HttpResponse:
    """Deja la pregunta de un comprador en la ficha del producto."""
    el_producto = get_object_or_404(ProductoTienda.objects.publicadas(), slug=slug)
    formulario = FormularioPregunta(request.POST)
    if formulario.is_valid():
        pregunta = formulario.save(commit=False)
        pregunta.producto = el_producto
        pregunta.save()
        messages.success(
            request, "Su pregunta quedó enviada: la respuesta se publica aquí mismo."
        )
    else:
        messages.error(request, "Revise la pregunta: falta algo o no se pudo enviar.")
    return redirect("tienda:producto", slug=slug)


@require_POST
def resenar(request: HttpRequest, slug: str) -> HttpResponse:
    """Deja una reseña; se publica cuando se aprueba."""
    el_producto = get_object_or_404(ProductoTienda.objects.publicadas(), slug=slug)
    formulario = FormularioResena(request.POST)
    if formulario.is_valid():
        resena = formulario.save(commit=False)
        resena.producto = el_producto
        resena.save()
        messages.success(
            request, "Gracias por la opinión: se publicará cuando la revisemos."
        )
    else:
        messages.error(request, "Revise la reseña: falta la calificación o el nombre.")
    return redirect("tienda:producto", slug=slug)


def seguimiento(request: HttpRequest) -> HttpResponse:
    """El estado de un pedido, con su número y el correo o la identificación."""
    numero = (request.GET.get("numero") or "").strip()
    contacto = (request.GET.get("contacto") or "").strip()
    pedido = None
    buscado = bool(numero or contacto)
    if buscado:
        pedido = _pedido_buscado(numero, contacto)
    contexto = {
        **_publico(),
        "pedido": pedido,
        "buscado": buscado,
        "numero": numero,
        "contacto": contacto,
    }
    return render(request, "tienda/seguimiento.html", contexto)


def _pedido_buscado(numero: str, contacto: str) -> Optional[Pedido]:
    """El pedido que coincide con el número y el correo o la identificación."""
    if not numero or not contacto:
        return None
    limpio = numero.upper().replace("P-", "").strip().lstrip("0")
    if not limpio.isdigit():
        return None
    return (
        Pedido.objects.select_related("factura")
        .prefetch_related("lineas")
        .filter(pk=int(limpio))
        .filter(Q(email__iexact=contacto) | Q(identificacion=contacto))
        .first()
    )


# ----------------------------------------------------------- las categorías


@login_required
@requiere_lectura("categorias_tienda")
def categorias(request: HttpRequest) -> HttpResponse:
    """El árbol de categorías, con lo que hay publicado en cada una."""
    lista = (
        Categoria.objects.select_related("padre")
        .annotate(cuantos=Count("productos"))
        .order_by("orden", "nombre")
    )
    contexto = {
        **marco(request),
        "categorias": lista,
        "cuantas": lista.count(),
        "activas": lista.filter(activa=True).count(),
    }
    return render(request, "tienda/categorias.html", contexto)


@login_required
@requiere_lectura("categorias_tienda")
def categoria_form(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Crear o corregir una categoría."""
    objeto = get_object_or_404(Categoria, pk=pk) if pk else Categoria()
    if request.method == "POST":
        exigir_escritura(request, "categorias_tienda")
        formulario = FormularioCategoria(request.POST, instance=objeto)
        if formulario.is_valid():
            guardada = formulario.save()
            messages.success(request, f"«{guardada.nombre}» quedó guardada.")
            return redirect("gestion_tienda:categorias")
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioCategoria(instance=objeto)

    contexto = {
        **marco(request),
        "formulario": formulario,
        "categoria": objeto,
        "es_nueva": pk is None,
    }
    return render(request, "tienda/categoria_form.html", contexto)


# --------------------------------------------------------------- los pedidos


@login_required
@requiere_lectura("pedidos")
def pedidos(request: HttpRequest) -> HttpResponse:
    """Los pedidos de la tienda, con lo que falta por facturar delante."""
    lista = Pedido.objects.select_related("cliente", "factura")
    estado = request.GET.get("estado") or ""
    texto = (request.GET.get("q") or "").strip()

    if estado == "pendientes":
        lista = lista.filter(anulado=False, factura__isnull=True)
    elif estado == "en_facturacion":
        lista = lista.filter(
            anulado=False, factura__isnull=False, factura__comprobante__isnull=True
        )
    elif estado == "facturados":
        lista = lista.filter(
            anulado=False, factura__comprobante__estado=EstadoComprobante.AUTORIZADO
        )
    elif estado == "anulados":
        lista = lista.filter(anulado=True)
    if texto:
        lista = lista.filter(
            Q(nombre__icontains=texto) | Q(identificacion__icontains=texto)
        )

    contexto = {
        **marco(request),
        "pedidos": lista,
        "estado": estado,
        "q": texto,
        "cuantos": lista.count(),
        "sin_facturar": Pedido.objects.filter(anulado=False, factura__isnull=True).count(),
    }
    return render(request, "tienda/pedidos.html", contexto)


@login_required
@requiere_lectura("pedidos")
def pedido(request: HttpRequest, pk: int) -> HttpResponse:
    """Un pedido, con lo que se pidió y lo que se cobra."""
    el_pedido = get_object_or_404(
        Pedido.objects.select_related("cliente", "factura").prefetch_related(
            "lineas__producto"
        ),
        pk=pk,
    )
    return render(
        request,
        "tienda/pedido.html",
        {**marco(request), "pedido": el_pedido},
    )


@login_required
@requiere_lectura("pedidos")
@require_POST
def facturar(request: HttpRequest, pk: int) -> HttpResponse:
    """Arma la factura del pedido y la abre para revisarla y emitirla."""
    exigir_escritura(request, "pedidos")
    el_pedido = get_object_or_404(Pedido, pk=pk)
    if el_pedido.factura_id:
        messages.info(request, "Ese pedido ya tiene factura.")
        return redirect("gestion_tienda:pedido", pk=pk)
    try:
        factura = factura_del_pedido(el_pedido)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("gestion_tienda:pedido", pk=pk)
    messages.info(
        request, "La factura quedó lista: revísela y emítala cuando esté conforme."
    )
    return redirect("facturacion:editar_factura", pk=factura.pk)


@login_required
@requiere_lectura("pedidos")
@require_POST
def anular(request: HttpRequest, pk: int) -> HttpResponse:
    """Deja el pedido sin efecto; el pedido no se borra."""
    exigir_escritura(request, "pedidos")
    el_pedido = get_object_or_404(Pedido, pk=pk)
    if el_pedido.factura_id:
        messages.error(request, "No se anula un pedido que ya tiene factura.")
    else:
        el_pedido.anulado = True
        el_pedido.save(update_fields=["anulado"])
        messages.success(request, "El pedido quedó anulado.")
    return redirect("gestion_tienda:pedido", pk=pk)


# ------------------------------------------------------------------ ayudas


def _publico() -> Dict[str, Any]:
    """Lo que lleva la cabecera y el pie de la tienda en todas sus pantallas."""
    emisor = conf.configuracion_activa()
    return {
        "emisor": emisor,
        "logo_empresa": _logo_de_la_empresa(emisor),
        "categorias_del_menu": Categoria.objects.filter(
            activa=True, padre__isnull=True
        ).prefetch_related("hijas"),
    }


def _logo_de_la_empresa(emisor: Any) -> str:
    """El logo que la empresa subió en su configuración del SRI, si lo hay.

    La tienda es del negocio, no de la aplicación: cuando hay logo propio se pone
    ese; si no, la plantilla se queda con el de Factiz.
    """
    from configuracion.models import LogoEmisor

    logo = LogoEmisor.de(emisor)
    return logo.url if logo is not None else ""


def _contexto_del_carrito(
    el_carrito: Carrito, lineas: Optional[List[LineaDelCarrito]] = None
) -> Dict[str, Any]:
    """Las líneas y los totales, calculados una sola vez."""
    lineas = el_carrito.lineas() if lineas is None else lineas
    subtotal = cuantizar(sum((linea.subtotal for linea in lineas), Decimal("0")))
    total = cuantizar(sum((linea.total for linea in lineas), Decimal("0")))
    return {
        "lineas": lineas,
        "subtotal": subtotal,
        "iva": cuantizar(total - subtotal),
        "total": total,
        "carrito": el_carrito,
    }


def _numero(valor: Decimal) -> str:
    """Una cantidad sin ceros de más, para el carrito: 3 y no 3.000."""
    return format(valor.normalize(), "f")


def _cantidad(valor: Optional[str]) -> Decimal:
    """Una cantidad escrita a mano: admite coma y no se cae con una letra."""
    if valor is None:
        return Decimal("0")
    try:
        return cuantizar(Decimal(str(valor).strip().replace(",", ".")), 3)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _identificadores(datos: Any) -> List[int]:
    """Los ids que trae el carrito en sus campos ``cantidad_<id>``."""
    ids: List[int] = []
    for clave in datos:
        if clave.startswith("cantidad_"):
            try:
                ids.append(int(clave.split("_", 1)[1]))
            except (TypeError, ValueError):
                continue
    return ids


# ------------------------------------------------------ preguntas y reseñas


@login_required
@requiere_lectura("preguntas_tienda")
def preguntas(request: HttpRequest) -> HttpResponse:
    """Las preguntas de la tienda, con lo que falta por responder delante."""
    lista = Pregunta.objects.select_related("producto", "respondida_por")
    estado = request.GET.get("estado") or "sin_responder"
    if estado == "sin_responder":
        lista = lista.filter(respuesta="")
    elif estado == "respondidas":
        lista = lista.exclude(respuesta="")
    elif estado == "ocultas":
        lista = lista.filter(publicada=False)

    contexto = {
        **marco(request),
        "preguntas": lista,
        "estado": estado,
        "cuantas": lista.count(),
        "sin_responder": Pregunta.objects.filter(respuesta="").count(),
    }
    return render(request, "tienda/preguntas.html", contexto)


@login_required
@requiere_lectura("preguntas_tienda")
@require_POST
def responder_pregunta(request: HttpRequest, pk: int) -> HttpResponse:
    """Contesta una pregunta; la respuesta sale en la ficha del producto."""
    exigir_escritura(request, "preguntas_tienda")
    pregunta = get_object_or_404(Pregunta, pk=pk)
    texto = (request.POST.get("respuesta") or "").strip()
    if not texto:
        messages.error(request, "Escriba la respuesta.")
    else:
        pregunta.responder(texto, request.user)
        messages.success(request, "La respuesta quedó publicada en la ficha.")
    return redirect("gestion_tienda:preguntas")


@login_required
@requiere_lectura("preguntas_tienda")
@require_POST
def publicar_pregunta(request: HttpRequest, pk: int) -> HttpResponse:
    """Muestra u oculta la pregunta sin borrarla."""
    exigir_escritura(request, "preguntas_tienda")
    pregunta = get_object_or_404(Pregunta, pk=pk)
    pregunta.publicada = not pregunta.publicada
    pregunta.save(update_fields=["publicada"])
    messages.success(
        request,
        "La pregunta quedó oculta." if not pregunta.publicada else "La pregunta quedó visible.",
    )
    return redirect("gestion_tienda:preguntas")


@login_required
@requiere_lectura("resenas_tienda")
def resenas(request: HttpRequest) -> HttpResponse:
    """Las reseñas, para aprobarlas o dejarlas fuera."""
    lista = Resena.objects.select_related("producto")
    estado = request.GET.get("estado") or "pendientes"
    if estado == "pendientes":
        lista = lista.filter(aprobada=False)
    elif estado == "aprobadas":
        lista = lista.filter(aprobada=True)

    contexto = {
        **marco(request),
        "resenas": lista,
        "estado": estado,
        "cuantas": lista.count(),
        "pendientes": Resena.objects.filter(aprobada=False).count(),
    }
    return render(request, "tienda/resenas.html", contexto)


@login_required
@requiere_lectura("resenas_tienda")
@require_POST
def moderar_resena(request: HttpRequest, pk: int) -> HttpResponse:
    """Aprueba o retira una reseña de la ficha."""
    exigir_escritura(request, "resenas_tienda")
    resena = get_object_or_404(Resena, pk=pk)
    resena.aprobada = request.POST.get("accion") == "aprobar"
    resena.save(update_fields=["aprobada"])
    messages.success(
        request,
        "La reseña quedó publicada." if resena.aprobada else "La reseña quedó retirada.",
    )
    return redirect("gestion_tienda:resenas")
