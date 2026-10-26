"""El orden del menú, también para los apartados.

El menú tiene los apartados escritos a mano para conservar sus iconos y sus
enlaces. Para que se puedan mover enteros sin reescribir la plantilla, cada
apartado y cada opción llevan un ``order`` de CSS sacado del campo ``orden``:
así el orden que se guarda al arrastrar vale igual para un apartado conocido
que para uno creado desde la aplicación.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from django import template
from django.db.models import Min
from personalize_options.models import Opcion

register = template.Library()


def _mapas(context: Any) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Los puestos de los apartados y el orden de cada opción.

    Se calcula una sola vez por petición: el menú se pinta dos veces (lateral y
    panel del móvil) y no tiene sentido consultar dos veces la misma tabla.
    """
    peticion = context.get("request")
    guardados = getattr(peticion, "_orden_del_menu", None) if peticion else None
    if guardados is not None:
        return guardados

    # El apartado va donde va su primera opción en el menú.
    filas = (
        Opcion.objects.filter(activo=True, en_menu=True)
        .values("grupo")
        .annotate(primero=Min("orden"))
        .order_by("primero", "grupo")
    )
    apartados = {fila["grupo"]: puesto for puesto, fila in enumerate(filas, start=1)}
    opciones = dict(
        Opcion.objects.filter(activo=True).values_list("clave", "orden")
    )
    guardados = (apartados, opciones)
    if peticion is not None:
        peticion._orden_del_menu = guardados
    return guardados


@register.simple_tag(takes_context=True)
def orden_apartado(context: Any, grupo: str) -> int:
    """El puesto del apartado dentro del menú (1 = primero)."""
    return _mapas(context)[0].get(grupo, 9999)


@register.simple_tag(takes_context=True)
def orden_opcion(context: Any, clave: str) -> int:
    """El orden de una opción dentro de su apartado."""
    return _mapas(context)[1].get(clave, 9998)
