"""El descuento del inventario cuando se emite una factura.

El paquete factura; el stock es cosa del negocio. Esta es la costura entre los dos:
al autorizarse una factura, lo que iba en ella sale del inventario y queda escrito
en el libro, con el comprobante apuntado para no descontarlo dos veces.

Se puede apagar: el ajuste ``inventario_descontar_al_facturar`` en «no» (se cambia
desde la administración), y entonces el
inventario solo se mueve a mano desde el libro de cada producto. El comando
``manage.py descontar_inventario`` sigue disponible para hacerlo cuando se pida.
"""

from __future__ import annotations

from typing import Any, List, Optional

from django.conf import settings
from personalize_options import ajustes
from factec.django.documentos import Factura
from factec.django.models import ComprobanteEmitido, EstadoComprobante

from .models import Existencia, Movimiento

__all__ = [
    "descontar_de_la_factura",
    "descuento_activo",
    "devolver_de_la_nota_credito",
    "facturas_sin_descontar",
    "quedaron_en_negativo",
]


def descuento_activo() -> bool:
    """¿Se descuenta el inventario al autorizarse una factura?"""
    return ajustes.booleano("inventario_descontar_al_facturar", False)


def descontar_de_la_factura(factura: Factura, usuario: Any = None) -> List[Movimiento]:
    """Saca del inventario lo que va en una factura ya autorizada.

    No hace nada si la factura no tiene comprobante (es un borrador), si el
    descuento está apagado en los ajustes o si esa factura ya descontó: se puede
    llamar sin miedo desde donde haga falta.
    """
    if not descuento_activo():
        return []
    return Movimiento.salida_por_factura(factura, usuario=usuario)


def devolver_de_la_nota_credito(nota: Any, usuario: Any = None) -> List[Movimiento]:
    """Devuelve al inventario lo que una nota de crédito saca de una factura.

    Va con el mismo interruptor: si el inventario no se descuenta al facturar, tampoco
    se devuelve al acreditar (el almacén lo lleva el negocio a mano). Es idempotente.
    """
    if not descuento_activo():
        return []
    return Movimiento.entrada_por_nota_credito(nota, usuario=usuario)


def quedaron_en_negativo(movimientos: List[Movimiento]) -> List[Existencia]:
    """Los bienes que se quedaron bajo cero con esos movimientos.

    No lo impide —un almacén a veces factura antes de que llegue la compra—, pero
    conviene decirlo: casi siempre es que faltaba cargar la entrada.
    """
    bajo_cero = []
    for movimiento in movimientos:
        existencia = getattr(movimiento.producto, "existencia", None)
        if existencia is not None and existencia.cantidad < 0:
            bajo_cero.append(existencia)
    return bajo_cero


def facturas_sin_descontar(factura: Optional[int] = None):
    """Facturas autorizadas a las que todavía les falta el movimiento de inventario.

    Sirve para el comando ``descontar_inventario``: recoge lo que quedó sin
    descontar cuando la emisión la hizo el worker de Celery o el admin.
    """
    descontadas = Movimiento.objects.filter(comprobante__isnull=False).values_list(
        "comprobante_id", flat=True
    )
    facturas = (
        Factura.objects.filter(
            comprobante__isnull=False, comprobante__estado=EstadoComprobante.AUTORIZADO
        )
        .exclude(comprobante_id__in=descontadas)
        .select_related("receptor", "comprobante")
        .order_by("pk")
    )
    if factura is not None:
        facturas = facturas.filter(pk=factura)
    return facturas
