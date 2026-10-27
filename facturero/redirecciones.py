"""Las direcciones de antes de la mudanza a ``/wadmin/``.

La aplicación se movió detrás de ``/wadmin/`` para dejar la raíz a la tienda. Los
marcadores y los enlaces que ya se habían repartido se quedaron con la dirección
vieja, y sin esto dan un 404: aquí se mandan a su sitio con un 301.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

__all__ = ["al_admin", "al_privado"]

#: Lo que ahora cuelga de ``/wadmin/`` y antes estaba en la raíz.
PRIVADOS = (
    "admin",
    "facturas",
    "facturar",
    "comprobantes",
    "catalogos",
    "inventario",
    "contabilidad",
    "caja",
    "supervision",
    "configuracion",
    "seguridad",
    "reportes",
)


def _con_la_cadena(request: HttpRequest, destino: str) -> str:
    consulta = request.META.get("QUERY_STRING") or ""
    return f"{destino}?{consulta}" if consulta else destino


def al_admin(request: HttpRequest, resto: str = "") -> HttpResponse:
    """El admin de Django, que ahora vive en ``/wadmin/admin/``."""
    return redirect(_con_la_cadena(request, "/wadmin/admin/" + resto), permanent=True)


def al_privado(request: HttpRequest, resto: str = "") -> HttpResponse:
    """Cualquier pantalla de la aplicación, que ahora vive detrás de ``/wadmin/``."""
    camino = request.path
    destino = "/wadmin" + camino
    return redirect(_con_la_cadena(request, destino), permanent=True)
