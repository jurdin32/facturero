"""La tienda en el admin: el producto de siempre, con su parte de web.

La extensión se edita desde la pantalla del producto —va como inline—, así que no
hay que darlo de alta dos veces: se abre el producto del catálogo fiscal y ahí
mismo se decide si sale a la web, con qué texto y a qué precio. La lista de
«productos de tienda» sirve para ver y ordenar lo ya publicado.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html
from factec.django.admin_documentos import ProductoAdmin as ProductoAdminFactec
from factec.django.documentos import Producto

from .models import (
    Categoria,
    ImagenProducto,
    LineaPedido,
    Pedido,
    Pregunta,
    ProductoTienda,
    Resena,
)

__all__ = [
    "CategoriaAdmin",
    "ImagenProductoAdmin",
    "PedidoAdmin",
    "ProductoAdmin",
    "ProductoTiendaAdmin",
]


def _dinero(valor: Decimal) -> str:
    """``1234.5`` → ``1.234,50``, como se escriben los importes aquí."""
    texto = f"{valor:,.2f}"
    return texto.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


class ImagenProductoInline(admin.TabularInline):
    """Las fotos del producto, en el mismo formulario."""

    model = ImagenProducto
    extra = 1
    fields = ("imagen", "alt", "orden")


class ProductoTiendaInline(admin.StackedInline):
    """La parte de tienda del producto, dentro de su pantalla del catálogo fiscal.

    Es la extensión del mismo producto: no crea otro, solo añade su fila de la web.
    """

    model = ProductoTienda
    fk_name = "producto_ptr"
    extra = 0
    max_num = 1
    show_change_link = True
    verbose_name = "en la tienda"
    verbose_name_plural = "en la tienda"
    autocomplete_fields = ("categoria",)
    fieldsets = (
        ("Publicación", {
            "fields": ("publicado", "destacado", "categoria", "orden", "slug"),
            "description": "Sin «publicado» el producto no sale a la tienda; se sigue "
                           "facturando igual.",
        }),
        ("Textos", {
            "fields": ("titulo", "resumen", "descripcion_larga"),
            "description": "El nombre de la web es opcional: si se deja vacío se usa "
                           "la descripción del producto.",
        }),
        ("Precio", {
            "fields": ("precio_web", "precio_oferta", "oferta_desde", "oferta_hasta"),
            "description": "Sin impuestos, como el precio del producto. La oferta solo "
                           "se aplica mientras esté vigente y sea menor.",
        }),
        ("Envío", {"fields": ("peso",)}),
    )


@admin.register(ProductoTienda)
class ProductoTiendaAdmin(admin.ModelAdmin):
    """Los productos publicados en la tienda, con su estado y su precio de venta.

    Aquí no se dan de alta: se publican desde la pantalla de su producto, para que
    el catálogo sea uno solo.
    """

    list_display = (
        "nombre", "codigo_principal", "categoria", "publicado", "destacado",
        "precio_mostrado", "con_stock", "orden",
    )
    list_display_links = ("nombre",)
    list_editable = ("publicado", "destacado", "orden")
    list_filter = (
        "publicado", "destacado", "tipo",
        ("categoria", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "titulo", "resumen", "slug", "codigo_principal", "codigo_auxiliar",
        "descripcion",
    )
    autocomplete_fields = ("categoria",)
    list_select_related = ("categoria", "existencia")
    readonly_fields = ("creado", "actualizado")
    inlines = [ImagenProductoInline]
    list_per_page = 50
    fieldsets = (
        ("Publicación", {
            "fields": ("publicado", "destacado", "categoria", "orden", "slug"),
            "description": "El producto y su precio fiscal se editan en el catálogo "
                           "del SRI; aquí se decide cómo se ve en la tienda.",
        }),
        ("Textos", {"fields": ("titulo", "resumen", "descripcion_larga")}),
        ("Precio", {
            "fields": ("precio_web", "precio_oferta", "oferta_desde", "oferta_hasta"),
            "description": "Sin impuestos, como el precio del producto. En la web se "
                           "muestra con el IVA ya sumado.",
        }),
        ("Envío", {"fields": ("peso",)}),
        ("Auditoría", {
            "classes": ("collapse",),
            "fields": ("creado", "actualizado"),
        }),
    )

    def has_add_permission(self, request: Any) -> bool:
        """Se publica desde el producto, no desde aquí: así no hay dos altas."""
        return False

    @admin.display(description="precio con IVA")
    def precio_mostrado(self, obj: ProductoTienda) -> str:
        """El precio como se ve en la web, con su oferta si la hay."""
        if not obj.oferta_vigente:
            return format_html("$ {}", _dinero(obj.precio))
        return format_html(
            '<span style="color:#888;text-decoration:line-through">$ {}</span> '
            "<strong>$ {}</strong>",
            _dinero(obj.precio_anterior),
            _dinero(obj.precio),
        )

    @admin.display(boolean=True, description="con stock")
    def con_stock(self, obj: ProductoTienda) -> bool:
        return obj.con_stock


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    """El árbol del catálogo: cada categoría cuelga de otra o va en el primer nivel."""

    list_display = ("ruta", "padre", "activa", "orden", "productos")
    list_filter = ("activa",)
    list_editable = ("activa", "orden")
    search_fields = ("nombre", "slug", "descripcion")
    autocomplete_fields = ("padre",)
    fieldsets = (
        (None, {"fields": ("nombre", "slug", "padre", "activa", "orden")}),
        ("Para la web", {"fields": ("descripcion",)}),
    )

    def get_queryset(self, request: Any) -> Any:
        return super().get_queryset(request).select_related("padre").annotate(
            _productos=Count("productos")
        )

    @admin.display(description="productos", ordering="_productos")
    def productos(self, obj: Categoria) -> int:
        return getattr(obj, "_productos", 0) or 0


@admin.register(ImagenProducto)
class ImagenProductoAdmin(admin.ModelAdmin):
    """Las fotos sueltas, para revisarlas o borrarlas de una en una."""

    list_display = ("descripcion", "producto", "orden")
    search_fields = ("alt", "producto__titulo", "producto__descripcion")
    autocomplete_fields = ("producto",)

    @admin.display(description="imagen")
    def descripcion(self, obj: ImagenProducto) -> str:
        return str(obj)


# El producto fiscal se registra aquí, con su parte de tienda al lado. ``factec``
# aplaza su propio registro hasta ``ready`` y respeta el que ponga el proyecto, así
# que este es el que queda.
if admin.site.is_registered(Producto):
    admin.site.unregister(Producto)


@admin.register(Producto)
class ProductoAdmin(ProductoAdminFactec):
    """El producto del catálogo fiscal, con su parte de tienda debajo."""

    inlines = [ProductoTiendaInline]

    list_display = tuple(ProductoAdminFactec.list_display) + ("en_la_tienda",)

    def get_queryset(self, request: Any) -> Any:
        return super().get_queryset(request).select_related("productotienda")

    @admin.display(boolean=True, description="en la tienda")
    def en_la_tienda(self, obj: Producto) -> bool:
        extension = getattr(obj, "productotienda", None)
        return bool(extension and extension.publicado)


class LineaPedidoInline(admin.TabularInline):
    """Lo que se pidió, tal como quedó al confirmar."""

    model = LineaPedido
    extra = 0
    can_delete = False
    fields = ("producto", "codigo", "descripcion", "cantidad", "precio_unitario", "tarifa_iva")
    readonly_fields = fields


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    """Los pedidos de la tienda, para consultarlos y seguirlos."""

    list_display = ("numero", "nombre", "identificacion", "total", "estado", "creado")
    list_filter = ("anulado", "creado")
    search_fields = ("nombre", "identificacion", "email", "telefono")
    date_hierarchy = "creado"
    readonly_fields = ("referencia", "cliente", "factura", "subtotal", "iva", "total", "creado")
    inlines = [LineaPedidoInline]
    list_per_page = 50
    fieldsets = (
        ("Quién compró", {
            "fields": ("nombre", "identificacion", "email", "telefono", "direccion"),
        }),
        ("El pedido", {
            "fields": ("nota", "subtotal", "iva", "total", "anulado"),
        }),
        ("Seguimiento", {
            "fields": ("cliente", "factura", "referencia", "creado"),
            "description": "La factura se arma desde la pantalla de pedidos, para "
                           "revisarla antes de emitirla.",
        }),
    )

    @admin.display(description="estado")
    def estado(self, obj: Pedido) -> str:
        return obj.estado


@admin.register(Pregunta)
class PreguntaAdmin(admin.ModelAdmin):
    list_display = ("producto", "nombre", "texto_corto", "estado", "creada")
    list_filter = ("publicada", "producto__categoria")
    search_fields = ("nombre", "texto", "respuesta", "producto__descripcion")
    readonly_fields = ("creada", "respondida", "respondida_por")
    list_per_page = 50

    @admin.display(description="pregunta")
    def texto_corto(self, obj: Pregunta) -> str:
        return obj.texto[:70]

    @admin.display(description="estado")
    def estado(self, obj: Pregunta) -> str:
        if not obj.publicada:
            return "oculta"
        return "respondida" if obj.contestada else "sin responder"


@admin.register(Resena)
class ResenaAdmin(admin.ModelAdmin):
    list_display = ("producto", "nombre", "calificacion", "aprobada", "creada")
    list_filter = ("aprobada", "calificacion", "producto__categoria")
    search_fields = ("nombre", "comentario", "producto__descripcion")
    readonly_fields = ("creada",)
    list_editable = ("aprobada",)
    list_per_page = 50
