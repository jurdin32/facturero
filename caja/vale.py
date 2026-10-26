"""El vale de caja, en PDF: el papel que se firma.

El vale es lo que justifica sacar efectivo de la caja o cobrarle un faltante a
alguien, así que se imprime: lleva el logo del emisor —o el de Factiz si no hay—,
el número, la fecha, quién responde, cuánto y por qué, y dos firmas.

Se escribe en **HTML** con la plantilla ``papel/vale.html``, la misma hoja de
estilo del acta de cierre y de los reportes: los tres se archivan juntos y tienen
que verse igual.
"""

from __future__ import annotations

from typing import Any

from factec.django import conf
from facturero.papel import logo_en_linea, papel
from reportes.tabla import dinero

__all__ = ["vale"]


def _nombre(usuario: Any) -> str:
    """El nombre de la persona, y si no lo tiene, el de la cuenta."""
    if usuario is None:
        return "—"
    return usuario.get_full_name().strip() or usuario.get_username()


def _cuadre(sesion: Any) -> str:
    """El cuadre de ese turno, dicho en palabras: esperado, contado y la diferencia."""
    if sesion is None:
        return ""
    diferencia = sesion.diferencia
    if diferencia < 0:
        juicio = f"faltante de $ {dinero(abs(diferencia))}"
    elif diferencia > 0:
        juicio = f"sobrante de $ {dinero(diferencia)}"
    else:
        juicio = "sin diferencia"
    return (
        f"esperado $ {dinero(sesion.saldo_esperado)}, "
        f"contado $ {dinero(sesion.saldo_declarado)}, {juicio}"
    )


def vale(el_vale: Any) -> bytes:
    """El PDF de ese vale de caja, listo para imprimir y firmar."""
    emisor = conf.configuracion_activa()
    empresa = getattr(emisor, "razon_social", "") or "Sin configuración del emisor"
    ruc = getattr(emisor, "ruc", "") or ""
    sesion = el_vale.sesion

    return papel(
        "papel/vale.html",
        {
            "logo": logo_en_linea(),
            "empresa": empresa,
            "ruc": ruc,
            "numero": el_vale.numero,
            "tipo": el_vale.get_tipo_display().upper(),
            "importe": dinero(el_vale.importe),
            "fecha": el_vale.fecha.strftime("%d/%m/%Y"),
            "estado": el_vale.get_estado_display(),
            "responsable": _nombre(el_vale.responsable),
            "turno": (
                sesion.cerrada_en.strftime("%d/%m/%Y %H:%M")
                if sesion is not None and sesion.cerrada_en
                else "—"
            ),
            "emitido_por": _nombre(el_vale.creado_por) if el_vale.creado_por else "—",
            "cobrado_el": (
                el_vale.cobrado_en.strftime("%d/%m/%Y") if el_vale.cobrado_en else "—"
            ),
            "motivo": el_vale.motivo or "—",
            "nota": el_vale.nota,
            "cuadre": _cuadre(sesion),
        },
    )
