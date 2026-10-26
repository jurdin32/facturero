"""Quién registró cada comprobante.

El paquete no guarda el usuario que escribe en la pantalla, así que se anota en
una tabla propia enlazada por el tipo y el id del comprobante. Los comprobantes
del SRI tienen códigos fijos (01 factura, 04 nota de crédito…), que es lo que se
guarda en ``RegistroComprobante.tipo``.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import RegistroComprobante


def _tipo(objeto: Any) -> str:
    return str(getattr(objeto, "TIPO_COMPROBANTE", "") or "")


def _numero(objeto: Any) -> str:
    comprobante = getattr(objeto, "comprobante", None)
    if comprobante is not None and getattr(comprobante, "secuencial", ""):
        return f"{comprobante.estab}-{comprobante.pto_emi}-{comprobante.secuencial}"
    secuencial = getattr(objeto, "secuencial", "") or ""
    return str(secuencial)


def _clave(objeto: Any) -> str:
    comprobante = getattr(objeto, "comprobante", None)
    if comprobante is not None and getattr(comprobante, "clave_acceso", ""):
        return str(comprobante.clave_acceso)
    return ""


def registrar(objeto: Any, usuario: Any) -> Optional[RegistroComprobante]:
    """Anota (o actualiza) el usuario de un comprobante ya guardado."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return None
    tipo = _tipo(objeto)
    if not tipo or not getattr(objeto, "pk", None):
        return None
    nombre = usuario.get_full_name() or usuario.get_username()
    registro, _ = RegistroComprobante.objects.update_or_create(
        tipo=tipo,
        objeto_id=objeto.pk,
        defaults={
            "numero": _numero(objeto),
            "clave_acceso": _clave(objeto),
            "usuario": usuario,
            "usuario_nombre": nombre,
        },
    )
    return registro


def de(objeto: Any) -> Optional[RegistroComprobante]:
    """El registro de usuario de un comprobante, si lo tiene."""
    tipo = _tipo(objeto)
    if not tipo or not getattr(objeto, "pk", None):
        return None
    return (
        RegistroComprobante.objects.filter(tipo=tipo, objeto_id=objeto.pk)
        .select_related("usuario")
        .first()
    )


def mapa(objetos: Any) -> dict[int, RegistroComprobante]:
    """Los registros de una lista de comprobantes, para no consultar uno a uno."""
    objetos = [objeto for objeto in objetos if getattr(objeto, "pk", None)]
    if not objetos:
        return {}
    tipo = _tipo(objetos[0])
    if not tipo:
        return {}
    return {
        registro.objeto_id: registro
        for registro in RegistroComprobante.objects.filter(
            tipo=tipo, objeto_id__in=[objeto.pk for objeto in objetos]
        ).select_related("usuario")
    }
