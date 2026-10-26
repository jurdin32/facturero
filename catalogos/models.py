"""Los códigos de retención que publica el SRI.

Cada retención lleva su código y su porcentaje, y los dos los fija el SRI según el
concepto: 303 honorarios al 10 %, 312 transferencia de bienes muebles al 2 %… No
es cosa de escribirlos de memoria, así que la tabla oficial se guarda aquí y de
aquí salen las opciones del comprobante de retención.

Se carga con ``python manage.py cargar_codigos_retencion``, que lee el archivo
oficial que está en ``catalogos/datos``.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any

from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

__all__ = [
    "CodigoRetencion",
    "IMPUESTOS_QUE_SE_RETIENEN",
    "opciones_de_retencion",
    "porcentajes_de_retencion",
]


#: Los impuestos que se retienen, con el código que les da el SRI en el comprobante.
IMPUESTOS_QUE_SE_RETIENEN = (("1", "Renta"), ("2", "IVA"), ("6", "ISD"))


def _porcentaje(valor: Any) -> str:
    """Un porcentaje como se dice: 10, 1.75, 0.5 (sin ceros de relleno)."""
    if valor is None:
        return ""
    numero = Decimal(valor).normalize()
    texto = format(numero, "f")
    return texto.replace(".", ",")


class CodigoRetencion(models.Model):
    """Un código de la tabla de retenciones en la fuente del SRI.

    El porcentaje puede venir vacío: hay conceptos en los que el SRI deja la
    tarifa al caso (pago a no residentes, por ejemplo) y entonces ``porcentaje_texto``
    dice lo que dice la tabla.
    """

    codigo = models.CharField(
        "Código",
        max_length=5,
        unique=True,
        help_text="El del SRI: 303, 304A, 9, 4580…",
    )
    concepto = models.CharField(
        "Concepto",
        max_length=300,
        help_text="El texto de la tabla oficial, tal cual.",
    )
    impuesto = models.CharField(
        "Impuesto",
        max_length=1,
        choices=IMPUESTOS_QUE_SE_RETIENEN,
        default="1",
    )
    porcentaje = models.DecimalField(
        "Porcentaje",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="El que fija el SRI para ese concepto.",
    )
    porcentaje_texto = models.CharField(
        "Porcentaje según el caso",
        max_length=160,
        blank=True,
        help_text="Lo que dice la tabla cuando la tarifa depende del caso.",
    )
    vigente_desde = models.DateField(
        "Vigente desde",
        null=True,
        blank=True,
        help_text="La fecha de la resolución que fijó estos porcentajes.",
    )
    orden = models.PositiveIntegerField(
        "Orden",
        default=0,
        help_text="El que lleva en la tabla del SRI, para listarlos igual.",
    )

    class Meta:
        verbose_name = "código de retención"
        verbose_name_plural = "códigos de retención"
        ordering = ["impuesto", "orden", "codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.concepto}"

    @property
    def como_porcentaje(self) -> str:
        """«10 %», o lo que diga la tabla cuando no hay una sola tarifa."""
        if self.porcentaje is not None:
            return f"{_porcentaje(self.porcentaje)} %"
        return self.porcentaje_texto

    @property
    def etiqueta(self) -> str:
        """Cómo se lee en la lista: «303 · Honorarios profesionales (10 %)»."""
        return f"{self.codigo} · {self.concepto} ({self.como_porcentaje})".replace(
            " ()", ""
        )


#: Los códigos se leen en cada fila de cada comprobante; la tabla no cambia salvo
#: cuando el SRI publica una resolución, así que se lee una vez y se guarda.


@lru_cache(maxsize=1)
def opciones_de_retencion() -> tuple[tuple[str, Any], ...]:
    """Los códigos agrupados por impuesto, en el orden de la tabla del SRI.

    Va primero la opción vacía: el primero de la lista no es el que se retiene, y
    ponerlo elegido sería decidir por quien está llenando el comprobante.
    """
    grupos: list[tuple[str, Any]] = [("", "Elija el concepto de la retención")]
    for codigo, nombre in IMPUESTOS_QUE_SE_RETIENEN:
        filas = tuple(
            (fila.codigo, fila.etiqueta)
            for fila in CodigoRetencion.objects.filter(impuesto=codigo)
        )
        if filas:
            grupos.append((nombre, filas))
    return tuple(grupos)


@lru_cache(maxsize=1)
def porcentajes_de_retencion() -> dict[str, tuple[str, str]]:
    """El porcentaje y el impuesto de cada código, para que se pongan solos."""
    return {
        fila.codigo: (
            str(fila.porcentaje) if fila.porcentaje is not None else "",
            fila.impuesto,
        )
        for fila in CodigoRetencion.objects.all()
    }


def olvidar_codigos_de_retencion() -> None:
    """Que la próxima lectura vuelva a la base (la llamó el comando o un cambio)."""
    opciones_de_retencion.cache_clear()
    porcentajes_de_retencion.cache_clear()


@receiver([post_save, post_delete], sender=CodigoRetencion)
def _la_tabla_cambio(sender: Any, **kwargs: Any) -> None:
    olvidar_codigos_de_retencion()
