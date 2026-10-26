"""Existencias y movimientos: el inventario del negocio.

El paquete ``factec`` factura, pero no lleva stock: qué se tiene, cuánto cuesta y
cuándo entró o salió es cosa del negocio. Aquí está lo mínimo que hace falta para
no perderle la cuenta:

* :class:`Existencia` — una fila por producto, con lo que hay y el mínimo a partir
  del cual conviene reponer.
* :class:`Movimiento` — el libro de entradas, salidas y ajustes. Es la historia: la
  cantidad de la existencia siempre es la suma de sus movimientos.

Los servicios no llevan inventario (no se agotan), así que solo los bienes tienen
existencia.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Case, DecimalField, F, Sum, When
from django.db.models.functions import Abs
from factec.django.documentos import Producto

__all__ = ["Existencia", "Movimiento", "TipoMovimiento"]


class TipoMovimiento(models.TextChoices):
    """Por qué se movió el stock."""

    ENTRADA = "entrada", "Entrada"
    SALIDA = "salida", "Salida"
    AJUSTE = "ajuste", "Ajuste"
    DEVOLUCION = "devolucion", "Devolución"
    FACTURA = "factura", "Salida por factura"


#: Qué signo tiene cada movimiento sobre la existencia.
SIGNO = {
    TipoMovimiento.ENTRADA.value: 1,
    TipoMovimiento.DEVOLUCION.value: 1,
    TipoMovimiento.SALIDA.value: -1,
    TipoMovimiento.FACTURA.value: -1,
    TipoMovimiento.AJUSTE.value: 1,     # el ajuste lleva el signo en la cantidad
}


class Existencia(models.Model):
    """Lo que hay de un producto, y el aviso de reposición."""

    producto = models.OneToOneField(
        Producto, verbose_name="producto", on_delete=models.CASCADE, related_name="existencia"
    )
    cantidad = models.DecimalField("cantidad", max_digits=16, decimal_places=3, default=0)
    minimo = models.DecimalField(
        "mínimo", max_digits=16, decimal_places=3, default=0,
        help_text="A partir de aquí conviene reponer. Con 0 no se avisa.",
    )
    ubicacion = models.CharField("ubicación", max_length=60, blank=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "existencia"
        verbose_name_plural = "existencias"
        ordering = ["producto__descripcion"]

    def __str__(self) -> str:
        return f"{self.producto.codigo_principal}: {self.cantidad}"

    @property
    def bajo_minimo(self) -> bool:
        """¿Hay que reponer?"""
        return self.minimo > 0 and self.cantidad <= self.minimo

    @property
    def cobertura(self) -> int:
        """Qué parte de lo deseable (el doble del mínimo) hay, para la barra.

        Con el mínimo se llega al 50 %: la barra se pone llena cuando se tiene el
        doble de lo que se necesita para no andar reponiendo a cada rato.
        """
        if self.minimo <= 0:
            return 0
        deseable = self.minimo * 2
        return max(0, min(100, round(float(self.cantidad / deseable) * 100)))

    @property
    def clase_cobertura(self) -> str:
        """La clase de la barra de progreso: verde si sobra, ámbar si va justo."""
        if self.cantidad <= 0:
            return "peligro"
        if self.bajo_minimo:
            return "cuidado"
        return "exito"

    @property
    def valor(self) -> Decimal:
        """Lo que vale lo que hay, al precio de venta del producto."""
        return (self.cantidad or Decimal("0")) * (self.producto.precio_unitario or Decimal("0"))

    @property
    def ultimo_movimiento(self) -> Optional["Movimiento"]:
        return self.producto.movimientos.first()


class Movimiento(models.Model):
    """Una línea del libro de inventario: lo que entró, salió o se ajustó.

    El movimiento no se edita: si se equivocó, se anula (que devuelve la cantidad a
    su sitio) y se hace uno nuevo. Así la existencia siempre cuadra con la historia.
    """

    producto = models.ForeignKey(
        Producto, verbose_name="producto", on_delete=models.CASCADE, related_name="movimientos"
    )
    fecha = models.DateField("fecha")
    tipo = models.CharField("tipo", max_length=12, choices=TipoMovimiento.choices)
    cantidad = models.DecimalField(
        "cantidad", max_digits=16, decimal_places=3,
        help_text="En un ajuste puede ser negativa: es lo que se suma a la existencia.",
    )
    costo_unitario = models.DecimalField(
        "costo unitario", max_digits=18, decimal_places=6, null=True, blank=True,
        help_text="Opcional: lo que costó cada unidad, para saber el valor del inventario.",
    )
    motivo = models.CharField("motivo", max_length=200, blank=True)
    referencia = models.CharField(
        "referencia", max_length=60, blank=True,
        help_text="Número de factura, de compra, de guía…",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="movimientos_de_inventario",
    )
    comprobante = models.ForeignKey(
        "sri_fe.ComprobanteEmitido", verbose_name="comprobante", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="movimientos_de_inventario",
        help_text=(
            "La factura autorizada que lo puso, si salió de una emisión. Sirve para "
            "no descontar dos veces el mismo comprobante."
        ),
    )
    creado = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "movimiento"
        verbose_name_plural = "movimientos"
        ordering = ["-fecha", "-pk"]
        indexes = [models.Index(fields=["producto", "-fecha"], name="inv_producto_fecha")]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} de {self.cantidad} · {self.producto}"

    # ------------------------------------------------------------ el stock

    def clean(self) -> None:
        if not self.pk and not self.cantidad:
            raise ValidationError({"cantidad": "Escriba cuánto se mueve."})
        if self.producto_id and self.producto.es_servicio:
            raise ValidationError(
                {"producto": "Un servicio no lleva inventario: solo se cuentan los bienes."}
            )

    def delta(self) -> Decimal:
        """Lo que este movimiento suma (o resta) a la existencia."""
        cantidad = self.cantidad or Decimal("0")
        signo = SIGNO.get(self.tipo, 1)
        if self.tipo == TipoMovimiento.AJUSTE.value:
            return cantidad          # el ajuste ya trae el signo
        return abs(cantidad) * signo

    def _existencia(self) -> Existencia:
        existencia, _ = Existencia.objects.get_or_create(producto=self.producto)
        return existencia

    def save(self, *args, **kwargs) -> None:
        creando = self._state.adding
        super().save(*args, **kwargs)
        if creando:
            self._aplicar(self.delta())

    def delete(self, *args, **kwargs):
        """Anular devuelve la cantidad a la existencia: el inventario no se descuadra."""
        if not self._state.adding:
            self._aplicar(-self.delta())
        return super().delete(*args, **kwargs)

    def _aplicar(self, delta: Decimal) -> None:
        existencia = self._existencia()
        existencia.cantidad = (existencia.cantidad or Decimal("0")) + delta
        existencia.save(update_fields=["cantidad", "actualizado"])

    # ------------------------------------------------------------------ ayudas

    @classmethod
    def ya_descontada(cls, comprobante) -> bool:
        """¿Este comprobante ya movió el inventario?"""
        return bool(comprobante) and cls.objects.filter(comprobante=comprobante).exists()

    @classmethod
    def salida_por_factura(cls, factura, usuario=None) -> list["Movimiento"]:
        """Lo que sale del inventario al emitir una factura.

        Solo se mueven las líneas que vienen de un producto del catálogo que sea un
        bien: los servicios no se agotan y lo escrito a mano no está inventariado.

        Es idempotente: si esa factura ya descontó, no vuelve a hacerlo. Se puede
        llamar sin miedo desde la emisión, desde el comando o a mano.
        """
        comprobante = factura.comprobante if factura.comprobante_id else None
        if comprobante is None:
            return []           # sin comprobante no hay factura emitida que descontar
        if cls.ya_descontada(comprobante):
            return []

        serie = f"{comprobante.estab}-{comprobante.pto_emi}-{comprobante.secuencial}"
        movimientos = []
        for linea in factura.detalles.all():
            if not linea.producto_id or linea.producto.es_servicio:
                continue
            movimientos.append(
                cls.objects.create(
                    producto=linea.producto,
                    fecha=factura.fecha_emision,
                    tipo=TipoMovimiento.FACTURA.value,
                    cantidad=linea.cantidad,
                    motivo=f"Facturado a {factura.receptor.razon_social}",
                    referencia=serie,
                    usuario=usuario,
                    comprobante=comprobante,
                )
            )
        return movimientos
    @classmethod
    def entrada_por_nota_credito(cls, nota, usuario=None) -> list["Movimiento"]:
        """Lo que vuelve al inventario cuando el cliente devuelve la mercadería.

        Mismo trato que la salida por factura, al revés: solo se mueven las líneas
        que vienen de un bien del catálogo. Es idempotente, así que se puede llamar
        sin miedo desde la emisión o desde el comando.
        """
        comprobante = nota.comprobante if nota.comprobante_id else None
        if comprobante is None:
            return []
        if cls.ya_descontada(comprobante):
            return []

        serie = f"{comprobante.estab}-{comprobante.pto_emi}-{comprobante.secuencial}"
        movimientos = []
        for linea in nota.detalles.all():
            if not linea.producto_id or linea.producto.es_servicio:
                continue
            movimientos.append(
                cls.objects.create(
                    producto=linea.producto,
                    fecha=nota.fecha_emision,
                    tipo=TipoMovimiento.DEVOLUCION.value,
                    cantidad=linea.cantidad,
                    motivo=f"Devuelto por {nota.receptor.razon_social}",
                    referencia=serie,
                    usuario=usuario,
                    comprobante=comprobante,
                )
            )
        return movimientos


#: El signo de cada movimiento, traducido a SQL para poder sumarlo de una vez.
DELTA_EN_SQL = Case(
    When(tipo=TipoMovimiento.AJUSTE.value, then=F("cantidad")),
    When(
        tipo__in=[TipoMovimiento.ENTRADA.value, TipoMovimiento.DEVOLUCION.value],
        then=Abs(F("cantidad")),
    ),
    default=-Abs(F("cantidad")),
    output_field=DecimalField(max_digits=18, decimal_places=3),
)


def cantidad_total(producto: Producto) -> Decimal:
    """Existencia calculada desde el libro (para comprobar que cuadra).

    Cuenta los signos: una salida de 3 resta 3, aunque en su fila esté escrita como 3.
    """
    total = producto.movimientos.aggregate(suma=Sum(DELTA_EN_SQL))
    return total["suma"] or Decimal("0")
