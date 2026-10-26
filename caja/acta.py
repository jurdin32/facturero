"""El acta de cierre de caja, en PDF.

Es el papel que se firma al terminar el turno: quién llevó la caja, cuándo la
abrió y la cerró, cuánto entró y salió, el desglose de los billetes y monedas
contados, el total, la diferencia, la revisión y los vales.

Se escribe en **HTML** —la plantilla ``papel/acta.html`` y la hoja de estilo de
imprenta ``static/css/papel.css``— y WeasyPrint la convierte en PDF. Lleva el logo
del emisor o, si no hay, el de Factiz, igual que los reportes: el acta se archiva
con la contabilidad y tiene que verse como el resto de los papeles.
"""

from __future__ import annotations

from typing import Any, Optional

from django.utils import timezone

from factec.django import conf
from facturero.papel import logo_en_linea, papel
from reportes.tabla import dinero

from .models import SesionCaja

__all__ = ["acta"]


def _nombre(usuario: Any) -> str:
    """El nombre de la persona, y si no lo tiene, el de la cuenta."""
    if usuario is None:
        return "—"
    return usuario.get_full_name().strip() or usuario.get_username()


def _fecha(valor: Any) -> str:
    if not valor:
        return "—"
    local = timezone.localtime(valor) if timezone.is_aware(valor) else valor
    return local.strftime("%d/%m/%Y %H:%M")


def acta(sesion: SesionCaja, movimientos: Any = None, completo: bool = True) -> bytes:
    """El PDF del acta de cierre de esa sesión.

    Con ``completo=False`` se imprime la versión del cajero: sólo el desglose de lo
    que contó, sin saldos ni diferencia. La versión entera —con el esperado, lo
    contado y lo que falta o sobra— es la de quien supervisa.
    """
    emisor = conf.configuracion_activa()
    empresa = getattr(emisor, "razon_social", "") or "Sin configuración del emisor"
    ruc = getattr(emisor, "ruc", "") or ""

    desglose = [
        {
            "valor": f"$ {dinero(renglon['valor'])}",
            "cantidad": renglon["cantidad"],
            "subtotal": f"$ {dinero(renglon['subtotal'])}",
        }
        for renglon in sesion.renglones_del_desglose
        if renglon["cantidad"]
    ]

    filas = []
    for movimiento in list(movimientos or [])[:40] if completo else []:
        filas.append(
            {
                "hora": _fecha(movimiento.fecha)[-5:],
                "tipo": movimiento.get_tipo_display(),
                "concepto": movimiento.concepto,
                "referencia": movimiento.referencia or "—",
                "importe": f"$ {dinero(movimiento.importe)}",
            }
        )

    diferencia = sesion.diferencia
    if diferencia:
        juicio = (
            f"El arqueo no cuadra: hay un {'FALTANTE' if diferencia < 0 else 'SOBRANTE'} "
            f"de $ {dinero(abs(diferencia))} frente al saldo esperado. "
            "Queda registrado para revisión."
        )
        clase = "falta"
    else:
        juicio = "El arqueo cuadra: lo contado es igual al saldo esperado."
        clase = "cuadra"

    revision = ""
    if sesion.revision != "sin_revisar":
        cuando = (
            timezone.localtime(sesion.revisada_en).strftime("%d/%m/%Y %H:%M")
            if sesion.revisada_en
            else "—"
        )
        revision = f"{sesion.get_revision_display()} · {_nombre(sesion.revisada_por)} · {cuando}"

    vales = [
        {
            "numero": vale.numero,
            "texto": (
                f"{vale.get_tipo_display()} de $ {dinero(vale.importe)} a "
                f"{_nombre(vale.responsable)}, {vale.get_estado_display().lower()} "
                f"({vale.motivo})."
            ),
        }
        for vale in (sesion.vales.exclude(estado="anulado") if sesion.pk else [])
    ]

    return papel(
        "papel/acta.html",
        {
            "logo": logo_en_linea(),
            "empresa": empresa,
            "ruc": ruc,
            "cajero": _nombre(sesion.usuario),
            "abierta": _fecha(sesion.abierta_en),
            "cerrada": _fecha(sesion.cerrada_en),
            "saldo_inicial": f"$ {dinero(sesion.saldo_inicial)}",
            "contado": f"$ {dinero(sesion.saldo_declarado)}",
            "ingresos": f"$ {dinero(sesion.total_ingresos)}",
            "egresos": f"$ {dinero(sesion.total_egresos)}",
            "esperado": f"$ {dinero(sesion.saldo_esperado)}",
            "diferencia": f"$ {dinero(diferencia)}",
            "completo": completo,
            "desglose": desglose,
            "movimientos": filas,
            "observaciones": sesion.observaciones_cierre,
            "juicio": juicio,
            "clase_diferencia": clase,
            "revision": revision,
            "nota_revision": sesion.nota_revision,
            "vales": vales,
        },
    )
