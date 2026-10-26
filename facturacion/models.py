"""Datos propios de la pantalla de facturación.

El paquete ``factec`` guarda los comprobantes; aquí se guarda quién los registró,
sin tocar las tablas del paquete. Es la trazabilidad que pide el control interno:
quién hizo cada transacción y cuándo.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class RegistroComprobante(models.Model):
    """El usuario que creó o actualizó un comprobante."""

    class Tipo(models.TextChoices):
        FACTURA = "01", "Factura"
        LIQUIDACION_COMPRA = "03", "Liquidación de compra"
        NOTA_CREDITO = "04", "Nota de crédito"
        NOTA_DEBITO = "05", "Nota de débito"
        GUIA_REMISION = "06", "Guía de remisión"
        RETENCION = "07", "Comprobante de retención"

    tipo = models.CharField("tipo", max_length=2, choices=Tipo.choices, db_index=True)
    objeto_id = models.PositiveBigIntegerField("id del comprobante")
    numero = models.CharField("número", max_length=30, blank=True)
    clave_acceso = models.CharField("clave de acceso", max_length=49, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="comprobantes_registrados",
    )
    usuario_nombre = models.CharField("nombre del usuario", max_length=150, blank=True)
    creado = models.DateTimeField("creado", auto_now_add=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "usuario del comprobante"
        verbose_name_plural = "usuarios de los comprobantes"
        ordering = ["-actualizado"]
        constraints = [
            models.UniqueConstraint(
                fields=["tipo", "objeto_id"], name="facturacion_usuario_comprobante"
            )
        ]

    def __str__(self) -> str:
        nombre = self.usuario_nombre or "sin usuario"
        return f"{self.get_tipo_display()} {self.numero or self.objeto_id} · {nombre}"
