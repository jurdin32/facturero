"""Lo que la tienda necesita en todas sus pantallas: el carrito y su contador."""

from __future__ import annotations

from typing import Any, Dict

from django.http import HttpRequest

from .carrito import Carrito

__all__ = ["carrito_en_la_cabecera"]


def carrito_en_la_cabecera(request: HttpRequest) -> Dict[str, Any]:
    """Deja el carrito en la plantilla, para el contador de la cabecera."""
    if not hasattr(request, "session"):
        return {"carrito": None, "carrito_unidades": 0}
    carrito = Carrito(request)
    return {"carrito": carrito, "carrito_unidades": carrito.unidades}
