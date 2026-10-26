"""Lo que cuesta lo que se vende, con el impuesto dentro.

El catálogo guarda el precio sin IVA, que es como lo pide el SRI en cada línea
del comprobante, pero quien lee una lista quiere saber cuánto paga. Aquí se
calcula, con el mismo redondeo que usa la factura.
"""

from __future__ import annotations

from decimal import Decimal

from factec.catalogos import PORCENTAJE_IVA
from factec.django.documentos import Producto
from factec.modelos import cuantizar

__all__ = ["precio_con_iva"]


def precio_con_iva(producto: Producto) -> Decimal:
    """El precio de una unidad con el IVA que le toca (el que paga el cliente)."""
    tasa = PORCENTAJE_IVA.get(producto.codigo_porcentaje_iva, Decimal("0"))
    return cuantizar(producto.precio_unitario * (Decimal("1") + tasa / Decimal("100")))
