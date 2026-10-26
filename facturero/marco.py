"""Lo común a todas las pantallas: quién emite y en qué ambiente.

Vive en la configuración del proyecto (no en una aplicación) porque lo usan las
tres: facturación, catálogos e inventario necesitan el mismo encabezado y el mismo
aviso cuando falta el emisor.
"""

from __future__ import annotations

from typing import Any, Optional

from django.http import HttpRequest
from factec.django import conf
from personalize_options import opciones
from personalize_options.permisos import Permisos

from . import sesion

__all__ = ["marco", "puede_emitir", "primera_pantalla"]


def marco(request: HttpRequest) -> dict[str, Any]:
    """Datos del encabezado: emisor activo, ambiente y si falta algo."""
    emisor = conf.configuracion_activa()
    ambiente = conf.ambiente()
    return {
        "emisor": emisor,
        "ambiente": ambiente,
        "es_produccion": int(ambiente) == 2,
        "sin_emisor": emisor is None,
        # Si el usuario tiene el turno de caja abierto: sin caja no se factura.
        "caja_abierta": _caja_abierta(request),
        # Los minutos que aguanta la pantalla sin bloquearse (0 = nunca).
        "limite_bloqueo": sesion.minutos_de_bloqueo(),
    }


def _caja_abierta(request: HttpRequest) -> bool:
    """Si el usuario que pide la pantalla tiene su caja del turno abierta."""
    from caja.servicios import sesion_abierta

    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return False
    return sesion_abierta(usuario) is not None


def puede_emitir(emisor: Any) -> Optional[str]:
    """Qué le falta al emisor para poder emitir (``None`` si no le falta nada).

    El certificado lo revisa el paquete: aquí solo se elige el primer problema para
    ponerlo en el aviso de la pantalla.
    """
    if emisor is None:
        return (
            "Todavía no hay una configuración del emisor. Cárguela en «Configuración "
            "del SRI» con el certificado .p12."
        )
    problemas = emisor.revisar_certificado().problemas
    if problemas:
        return problemas[0]
    if emisor.ambiente != conf.ambiente():
        return (
            f"El emisor activo es del ambiente {emisor.get_ambiente_display()} y los "
            "ajustes apuntan a otro: revise cuál está activo."
        )
    return None


def primera_pantalla(permisos: Permisos) -> Optional[str]:
    """La primera pantalla que este usuario puede abrir (``None`` si no hay ninguna).

    Sirve para el tablero: si alguien entra y no puede verlo, no se le puede dejar en
    un 403 en la puerta; se le lleva a lo primero que sí puede mirar.
    """
    for clave, opcion in opciones.por_clave(solo_activas=True).items():
        if clave == "tablero" or not getattr(opcion, "en_menu", False):
            continue
        if permisos.puede_leer(clave) and getattr(opcion, "url", ""):
            return opcion.url
    return None
