"""El catálogo de la tienda: el mismo producto de siempre, con lo que la web pide.

El producto ya está definido en ``factec`` —código, descripción, unidad, precio sin
impuestos, tarifa de IVA, si es bien o servicio, si está activo— y no se duplica
aquí. :class:`ProductoTienda` **hereda** de él: es el mismo producto (misma fila,
mismo código, mismo IVA, mismo stock) más lo que el SRI no necesita y una tienda sí:

* :class:`Categoria` — el árbol con el que se navega el catálogo.
* :class:`ProductoTienda` — la extensión del producto: textos de la web, categoría,
  precio de venta y oferta, si se publica.
* :class:`ImagenProducto` — las fotos, en orden; la primera es la principal.

Un producto sin extensión se factura igual y no aparece en la tienda; se publica
—es decir, se extiende— desde su propia pantalla del admin
(:meth:`ProductoTienda.de` y :meth:`ProductoTienda.extender`). La facturación no se
entera: sigue viendo los mismos productos.

El precio de la tienda se guarda **sin impuestos**, igual que el del producto;
:attr:`ProductoTienda.precio` y :attr:`ProductoTienda.precio_anterior` lo devuelven
con IVA, que es como se muestra en una tienda.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Avg
from django.utils import timezone
from django.utils.text import slugify
from factec.catalogos import PORCENTAJE_IVA
from factec.django.documentos import Cliente, Producto
from factec.django.models import EstadoComprobante
from factec.modelos import cuantizar

from .texto import markdown_a_html

__all__ = [
    "Categoria",
    "ProductoTienda",
    "ImagenProducto",
    "Pedido",
    "LineaPedido",
    "EXTENSIONES_IMAGEN",
    "TAMANO_MAXIMO_IMAGEN",
    "ids_de_la_rama",
]

#: Lo que se acepta subir como foto. El SVG se deja fuera a propósito: puede traer
#: guion, y una foto de producto no lo necesita.
EXTENSIONES_IMAGEN = ("png", "jpg", "jpeg", "webp", "avif")

#: 5 MB: una foto de catálogo cabe de sobra y no hincha la copia de seguridad.
TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024


def validar_tamano(archivo: object) -> None:
    """Una foto de más de cinco megas es una foto sin recortar."""
    if archivo and getattr(archivo, "size", 0) > TAMANO_MAXIMO_IMAGEN:
        raise ValidationError("La imagen no puede pasar de 5 MB. Redúzcala un poco.")


def _slug_libre(modelo: type[models.Model], base: str, propio: Optional[int]) -> str:
    """Una dirección que no choque con la de otra fila del mismo modelo.

    El slug es la dirección del producto y no debe cambiar al cambiar el nombre, así
    que solo se genera cuando está vacío. Si el nombre ya está tomado se numera:
    ``camiseta-azul``, ``camiseta-azul-2``…
    """
    maximo = modelo._meta.get_field("slug").max_length or 120
    raiz = slugify(base)[:maximo].strip("-") or "producto"
    candidato, numero = raiz, 2
    otros = modelo.objects.exclude(pk=propio)
    while otros.filter(slug=candidato).exists():
        sufijo = f"-{numero}"
        candidato = raiz[: maximo - len(sufijo)].rstrip("-") + sufijo
        numero += 1
    return candidato


def _precio_o_nada(valor: Optional[Decimal]) -> Decimal:
    return valor if valor is not None else Decimal("0")


class Categoria(models.Model):
    """Un estante del catálogo, que puede colgar de otro.

    El árbol es libre: «Ropa › Camisetas › Manga corta». La categoría de arriba se
    puede dejar vacía, y ahí termina la rama.
    """

    nombre = models.CharField("nombre", max_length=80)
    slug = models.SlugField(
        "dirección",
        max_length=80,
        unique=True,
        blank=True,
        help_text="Lo que va en la dirección de la web. Si se deja vacío se arma con el nombre.",
    )
    descripcion = models.CharField(
        "descripción",
        max_length=300,
        blank=True,
        help_text="Opcional: un párrafo para la cabecera de la categoría.",
    )
    padre = models.ForeignKey(
        "self",
        verbose_name="categoría de arriba",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hijas",
        help_text="Vacío para una categoría de primer nivel.",
    )
    activa = models.BooleanField(
        "activa",
        default=True,
        help_text="Una categoría inactiva no se ofrece en el menú de la tienda.",
    )
    orden = models.PositiveIntegerField(
        "orden", default=0, help_text="Las de número menor salen primero."
    )

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["orden", "nombre"]

    def __str__(self) -> str:
        return self.ruta

    @property
    def ruta(self) -> str:
        """«Ropa › Camisetas › Manga corta», subiendo por las categorías de arriba."""
        partes: List[str] = []
        vistas = set()
        actual: Optional[Categoria] = self
        while actual is not None and actual.pk not in vistas:
            vistas.add(actual.pk)
            partes.append(actual.nombre)
            actual = actual.padre
        return " › ".join(reversed(partes))

    def clean(self) -> None:
        super().clean()
        if not self.pk or not self.padre_id:
            return
        if self.padre_id == self.pk:
            raise ValidationError({"padre": "Una categoría no puede colgar de sí misma."})
        vistas = {self.pk}
        actual = self.padre
        while actual is not None:
            if actual.pk in vistas:
                raise ValidationError(
                    {"padre": "La categoría no puede colgar de una de sus hijas."}
                )
            vistas.add(actual.pk)
            actual = actual.padre

    def save(self, *args: object, **kwargs: object) -> None:
        if not (self.slug or "").strip():
            self.slug = _slug_libre(Categoria, self.nombre, self.pk)
        super().save(*args, **kwargs)

    def con_descendientes(self) -> List[int]:
        """Los identificadores de esta categoría y de todo lo que cuelga de ella."""
        return ids_de_la_rama(self)


def ids_de_la_rama(categoria: Optional[Categoria]) -> List[int]:
    """Los ids de una categoría y sus subcategorías, para filtrar el catálogo."""
    if categoria is None or not categoria.pk:
        return []
    ids: List[int] = []
    pendientes = [categoria.pk]
    while pendientes:
        actual = pendientes.pop()
        if actual in ids:
            continue
        ids.append(actual)
        pendientes.extend(
            Categoria.objects.filter(padre_id=actual).values_list("pk", flat=True)
        )
    return ids


class CatalogoQuerySet(models.QuerySet):
    """Las consultas que hace la tienda: lo publicado, lo destacado, por categoría."""

    def publicadas(self) -> "CatalogoQuerySet":
        """Lo que se puede enseñar: publicado y con el producto todavía activo."""
        return self.filter(publicado=True, activo=True)

    def destacadas(self) -> "CatalogoQuerySet":
        """Lo publicado que va en la portada."""
        return self.publicadas().filter(destacado=True)

    def en_categoria(self, categoria: Optional[Categoria]) -> "CatalogoQuerySet":
        """Lo publicado en esa categoría o en cualquiera de sus subcategorías."""
        ids = ids_de_la_rama(categoria)
        if not ids:
            return self.none()
        return self.publicadas().filter(categoria_id__in=ids)


class ProductoTienda(Producto):
    """El producto del catálogo fiscal, extendido con lo que la tienda necesita.

    Se hereda de :class:`factec.django.documentos.Producto`: mismo ``pk``, mismo
    código, mismo precio fiscal, mismo inventario. Heredar no cambia cómo se
    factura; solo añade las columnas de la web.
    """

    slug = models.SlugField(
        "dirección",
        max_length=120,
        unique=True,
        blank=True,
        help_text="Lo que va en la dirección de la web. Si se deja vacío se arma con el nombre.",
    )
    titulo = models.CharField(
        "nombre en la web",
        max_length=120,
        blank=True,
        help_text="Opcional. Si se deja vacío se usa la descripción del producto.",
    )
    resumen = models.CharField(
        "resumen",
        max_length=300,
        blank=True,
        help_text="Una o dos líneas para los listados y el buscador.",
    )
    descripcion_larga = models.TextField(
        "descripción larga",
        blank=True,
        help_text="El texto de la ficha: materiales, medidas, qué incluye…",
    )
    categoria = models.ForeignKey(
        Categoria,
        verbose_name="categoría",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="productos",
        help_text="Dónde se encuentra en el menú de la tienda.",
    )
    publicado = models.BooleanField(
        "publicado",
        default=False,
        help_text="Nada sale a la web hasta que se marque: la tienda se enciende producto a producto.",
    )
    destacado = models.BooleanField(
        "destacado", default=False, help_text="Para la portada de la tienda."
    )
    orden = models.PositiveIntegerField(
        "orden",
        default=0,
        help_text="Dentro de su categoría, los de número menor salen primero.",
    )
    precio_web = models.DecimalField(
        "precio en la web",
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=(
            "Sin impuestos, como el del producto. Si se deja vacío se usa el precio "
            "del producto fiscal."
        ),
    )
    precio_oferta = models.DecimalField(
        "precio de oferta",
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Sin impuestos. Solo se aplica mientras la oferta esté vigente y sea menor.",
    )
    oferta_desde = models.DateField(
        "oferta desde", null=True, blank=True, help_text="Vacío: la oferta empieza ya."
    )
    oferta_hasta = models.DateField(
        "oferta hasta", null=True, blank=True, help_text="Vacío: la oferta no caduca."
    )
    peso = models.DecimalField(
        "peso (kg)",
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Opcional: para calcular el envío.",
    )

    objects = CatalogoQuerySet.as_manager()

    class Meta:
        verbose_name = "producto de tienda"
        verbose_name_plural = "productos de tienda"
        ordering = ["orden", "pk"]
        indexes = [
            models.Index(fields=["publicado", "orden"], name="tienda_publicado_orden")
        ]

    def __str__(self) -> str:
        return self.nombre

    def save(self, *args: object, **kwargs: object) -> None:
        if not (self.slug or "").strip():
            self.slug = _slug_libre(ProductoTienda, self.nombre, self.pk)
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if (
            self.oferta_desde is not None
            and self.oferta_hasta is not None
            and self.oferta_hasta < self.oferta_desde
        ):
            raise ValidationError(
                {"oferta_hasta": "La oferta no puede terminar antes de empezar."}
            )
        if self.precio_oferta is not None and self.precio_oferta >= self.precio_base_sin_iva:
            raise ValidationError(
                {"precio_oferta": "Una oferta tiene que ser menor que el precio normal."}
            )

    # -------------------------------------------------- extendido desde el producto

    @classmethod
    def de(cls, producto: Optional[Producto]) -> Optional["ProductoTienda"]:
        """La extensión de ese producto, si ya se publicó; ``None`` si no."""
        if producto is None or not producto.pk:
            return None
        return cls.objects.filter(pk=producto.pk).first()

    @classmethod
    def extender(cls, producto: Producto) -> "ProductoTienda":
        """Publica un producto que ya existe, sin duplicarlo.

        Crea la fila de la tienda enlazada al mismo producto, con los datos que ya
        tenía. Es idempotente: si ya estaba extendido, devuelve la extensión.
        """
        ficha = cls.de(producto)
        if ficha is not None:
            return ficha
        ficha = cls(producto_ptr=producto)
        # Al guardar la extensión, Django escribe también la fila del producto: hay
        # que llevar los campos heredados tal como están para no vaciarlos.
        for campo in Producto._meta.concrete_fields:
            setattr(ficha, campo.attname, getattr(producto, campo.attname))
        ficha.save(force_insert=True)
        return ficha

    # ------------------------------------------------------------ cómo se llama

    @property
    def nombre(self) -> str:
        """El nombre que se ve en la web."""
        return (self.titulo or "").strip() or self.descripcion

    # ------------------------------------------------------------- los precios

    @property
    def tarifa_iva(self) -> Decimal:
        """El porcentaje de IVA del producto, según el catálogo del SRI."""
        return PORCENTAJE_IVA.get(str(self.codigo_porcentaje_iva), Decimal("0"))

    @property
    def precio_base_sin_iva(self) -> Decimal:
        """El precio normal, sin impuestos: el de la web o, si no hay, el fiscal."""
        if self.precio_web is not None:
            return self.precio_web
        return _precio_o_nada(self.precio_unitario)

    @property
    def oferta_vigente(self) -> bool:
        """¿La oferta se aplica hoy?"""
        if self.precio_oferta is None:
            return False
        hoy = timezone.localdate()
        if self.oferta_desde is not None and hoy < self.oferta_desde:
            return False
        if self.oferta_hasta is not None and hoy > self.oferta_hasta:
            return False
        return self.precio_oferta < self.precio_base_sin_iva

    @property
    def precio_sin_iva(self) -> Decimal:
        """Lo que se cobra, sin impuestos: la oferta si está vigente; si no, el normal."""
        if self.oferta_vigente:
            return _precio_o_nada(self.precio_oferta)
        return self.precio_base_sin_iva

    @property
    def precio_anterior_sin_iva(self) -> Optional[Decimal]:
        """El precio normal cuando hay oferta, para tacharlo al lado."""
        return self.precio_base_sin_iva if self.oferta_vigente else None

    @property
    def precio(self) -> Decimal:
        """El precio de venta **con IVA**, que es como se muestra en la tienda."""
        return self._con_iva(self.precio_sin_iva)

    @property
    def precio_anterior(self) -> Optional[Decimal]:
        """El precio de antes con IVA, o ``None`` si no hay oferta."""
        anterior = self.precio_anterior_sin_iva
        return self._con_iva(anterior) if anterior is not None else None

    @property
    def descuento(self) -> int:
        """El «-15 %» de la etiqueta; 0 si no hay oferta."""
        anterior = self.precio_anterior_sin_iva
        if anterior is None or anterior <= 0:
            return 0
        return round(float((anterior - self.precio_sin_iva) / anterior) * 100)

    def _con_iva(self, valor: Decimal) -> Decimal:
        return cuantizar(valor * (1 + self.tarifa_iva / Decimal("100")))

    # --------------------------------------------------------------- el stock

    @property
    def con_stock(self) -> bool:
        """¿Se puede pedir hoy?

        Un servicio nunca se agota. De un bien se mira su existencia; si el negocio no
        lleva inventario de ese bien (no hay fila de existencia), se da por disponible
        y no se inventa un «agotado» que nadie dijo.
        """
        if self.es_servicio:
            return True
        existencia = getattr(self, "existencia", None)
        if existencia is None:
            return True
        return (existencia.cantidad or Decimal("0")) > 0

    # -------------------------------------------------------------- las fotos

    @property
    def imagen_principal(self) -> Optional["ImagenProducto"]:
        """La primera foto, que es la que sale en el listado."""
        return self.imagenes.first()

    @property
    def publicado_en_la_web(self) -> bool:
        """¿Sale hoy en la tienda? La ficha tiene que estar publicada y el producto activo."""
        return bool(self.publicado and self.activo)

    @property
    def descripcion_html(self) -> str:
        """La descripción larga, escrita en Markdown, ya convertida y limpia."""
        return markdown_a_html(self.descripcion_larga)

    @property
    def resenas_aprobadas(self) -> Any:
        return self.resenas.filter(aprobada=True)

    @property
    def promedio_resenas(self) -> Optional[float]:
        """Las estrellas medias, o ``None`` si todavía no hay opiniones."""
        promedio = self.resenas.filter(aprobada=True).aggregate(
            promedio=Avg("calificacion")
        )["promedio"]
        return round(promedio, 1) if promedio is not None else None

    @property
    def total_resenas(self) -> int:
        return self.resenas.filter(aprobada=True).count()

    @property
    def preguntas_publicadas(self) -> Any:
        return self.preguntas.filter(publicada=True)


class ImagenProducto(models.Model):
    """Una foto del producto de tienda. La de menor orden es la principal."""

    producto = models.ForeignKey(
        ProductoTienda,
        verbose_name="producto",
        on_delete=models.CASCADE,
        related_name="imagenes",
    )
    imagen = models.FileField(
        "imagen",
        upload_to="tienda/productos/",
        validators=[
            FileExtensionValidator(
                EXTENSIONES_IMAGEN, "La imagen tiene que ser PNG, JPG, WEBP o AVIF."
            ),
            validar_tamano,
        ],
        help_text="PNG, JPG, WEBP o AVIF, hasta 5 MB.",
    )
    alt = models.CharField(
        "texto alternativo",
        max_length=160,
        blank=True,
        help_text="Lo que se lee cuando la imagen no carga. Ayuda al buscador.",
    )
    orden = models.PositiveIntegerField(
        "orden", default=0, help_text="La de número menor es la principal."
    )

    class Meta:
        verbose_name = "imagen"
        verbose_name_plural = "imágenes"
        ordering = ["orden", "pk"]

    def __str__(self) -> str:
        return self.alt or f"Imagen de {self.producto_id}"


# ------------------------------------------------------------------- los pedidos


class Pedido(models.Model):
    """Lo que alguien pidió en la tienda, antes de facturarlo.

    Guarda los datos del comprador y el precio de cada línea como estaban al
    confirmar: si mañana cambia el precio en la web, el pedido de ayer sigue
    diciendo lo que se cobró. Facturarlo es cosa de la aplicación, no de la tienda.
    """

    referencia = models.UUIDField(
        "referencia", default=uuid.uuid4, unique=True, editable=False,
        help_text="La que va en la dirección del acuse, para no adivinarla.",
    )
    nombre = models.CharField("nombre", max_length=160)
    identificacion = models.CharField(
        "identificación", max_length=20, blank=True,
        help_text="RUC o cédula. Vacía si compra como consumidor final.",
    )
    email = models.EmailField("correo", blank=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    direccion = models.CharField("dirección de entrega", max_length=300, blank=True)
    nota = models.TextField("nota", blank=True, help_text="Lo que dejó dicho el cliente.")
    cliente = models.ForeignKey(
        Cliente,
        verbose_name="cliente",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pedidos_de_tienda",
        help_text="Al que se le factura: se busca por la identificación o se crea.",
    )
    factura = models.OneToOneField(
        "sri_fe.Factura",
        verbose_name="factura",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pedido_de_tienda",
        help_text="La factura que salió de este pedido, si ya se hizo.",
    )
    anulado = models.BooleanField(
        "anulado", default=False, help_text="Un pedido anulado no se factura."
    )
    subtotal = models.DecimalField(
        "subtotal", max_digits=14, decimal_places=2, default=0,
        help_text="Sin impuestos, como estaba al confirmar.",
    )
    iva = models.DecimalField("IVA", max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField("total", max_digits=14, decimal_places=2, default=0)
    creado = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-creado", "-pk"]
        indexes = [models.Index(fields=["anulado", "-creado"], name="tienda_pedido_fecha")]

    def __str__(self) -> str:
        return f"{self.numero} · {self.nombre}"

    @property
    def numero(self) -> str:
        """El número que se le da al cliente: ``P-000123``."""
        return f"P-{self.pk:06d}"

    @property
    def facturado(self) -> bool:
        """¿La factura de este pedido ya está autorizada por el SRI?"""
        if not self.factura_id:
            return False
        comprobante = getattr(self.factura, "comprobante", None)
        return bool(comprobante and comprobante.estado == EstadoComprobante.AUTORIZADO)

    @property
    def estado(self) -> str:
        """Cómo va: pendiente, en facturación, facturado o anulado."""
        if self.anulado:
            return "Anulado"
        if self.factura_id:
            return "Facturado" if self.facturado else "En facturación"
        return "Pendiente"

    @property
    def se_puede_facturar(self) -> bool:
        return not self.anulado and not self.factura_id

    def calcular_totales(self) -> None:
        """Suma las líneas y deja el total escrito en el pedido."""
        lineas = list(self.lineas.all())
        self.subtotal = cuantizar(sum((linea.subtotal for linea in lineas), Decimal("0")))
        self.iva = cuantizar(sum((linea.iva for linea in lineas), Decimal("0")))
        self.total = cuantizar(self.subtotal + self.iva)


class LineaPedido(models.Model):
    """Un producto del pedido, con el precio y el IVA que tenía en la web."""

    pedido = models.ForeignKey(
        Pedido, verbose_name="pedido", on_delete=models.CASCADE, related_name="lineas"
    )
    producto = models.ForeignKey(
        ProductoTienda,
        verbose_name="producto",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lineas_de_pedido",
        help_text="Si el producto se borra, la línea conserva lo que se vendió.",
    )
    codigo = models.CharField("código", max_length=25, blank=True)
    descripcion = models.CharField("descripción", max_length=300)
    cantidad = models.DecimalField("cantidad", max_digits=18, decimal_places=3, default=1)
    precio_unitario = models.DecimalField(
        "precio unitario", max_digits=18, decimal_places=6, default=0,
        help_text="Sin impuestos, como estaba en la web.",
    )
    tarifa_iva = models.DecimalField(
        "tarifa de IVA", max_digits=5, decimal_places=2, default=0,
        help_text="El porcentaje que se aplicó.",
    )

    class Meta:
        verbose_name = "línea del pedido"
        verbose_name_plural = "líneas del pedido"
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"{self.descripcion} × {self.cantidad}"

    @property
    def subtotal(self) -> Decimal:
        """Cantidad por precio, sin impuestos."""
        return cuantizar(self.cantidad * self.precio_unitario)

    @property
    def iva(self) -> Decimal:
        return cuantizar(self.subtotal * self.tarifa_iva / Decimal("100"))

    @property
    def total(self) -> Decimal:
        return cuantizar(self.subtotal + self.iva)


# ------------------------------------------------------ preguntas y reseñas


class Pregunta(models.Model):
    """Lo que alguien pregunta sobre un producto antes de comprarlo.

    Se responde desde la aplicación y la respuesta se ve en la ficha, junto a la
    pregunta. Nada se publica sin que el vendedor conteste.
    """

    producto = models.ForeignKey(
        ProductoTienda,
        verbose_name="producto",
        on_delete=models.CASCADE,
        related_name="preguntas",
    )
    nombre = models.CharField("nombre", max_length=120)
    email = models.EmailField("correo", blank=True)
    texto = models.TextField("pregunta", max_length=1000)
    respuesta = models.TextField("respuesta", max_length=2000, blank=True)
    publicada = models.BooleanField(
        "publicada", default=True, help_text="Se puede ocultar sin borrarla."
    )
    respondida = models.DateTimeField("respondida", null=True, blank=True)
    respondida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="quién respondió",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="preguntas_respondidas",
    )
    creada = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "pregunta"
        verbose_name_plural = "preguntas"
        ordering = ["-creada", "-pk"]

    def __str__(self) -> str:
        return f"{self.nombre}: {self.texto[:60]}"

    @property
    def contestada(self) -> bool:
        return bool(self.respuesta.strip())

    def responder(self, texto: str, usuario: Any = None) -> None:
        """Deja la respuesta y quién la escribió."""
        self.respuesta = (texto or "").strip()
        self.respondida = timezone.now()
        self.respondida_por = usuario
        self.save(update_fields=["respuesta", "respondida", "respondida_por"])


class Resena(models.Model):
    """La opinión de quien compró, con su calificación de una a cinco.

    No se publica sola: queda pendiente hasta que se aprueba, para que la ficha no
    se llene de lo que no tiene que ver con el producto.
    """

    producto = models.ForeignKey(
        ProductoTienda,
        verbose_name="producto",
        on_delete=models.CASCADE,
        related_name="resenas",
    )
    nombre = models.CharField("nombre", max_length=120)
    email = models.EmailField("correo", blank=True)
    calificacion = models.PositiveSmallIntegerField(
        "calificación",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="De 1 a 5 estrellas.",
    )
    comentario = models.TextField("comentario", max_length=2000)
    aprobada = models.BooleanField(
        "aprobada", default=False, help_text="Solo las aprobadas salen en la ficha."
    )
    creada = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "reseña"
        verbose_name_plural = "reseñas"
        ordering = ["-creada", "-pk"]

    def __str__(self) -> str:
        return f"{self.calificacion}★ · {self.nombre}"

    @property
    def estrellas(self) -> str:
        """«★★★★☆», para pintarlas sin imágenes."""
        llenas = "★" * self.calificacion
        vacias = "☆" * (5 - self.calificacion)
        return f"{llenas}{vacias}"
