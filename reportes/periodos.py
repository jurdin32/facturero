"""El período que se pide en los reportes.

Un reporte sirve para un tramo de fechas, y ese tramo se elige de dos maneras: con
un período de los de siempre —la semana, el mes, el trimestre, el año— o con un
rango escrito a mano. Aquí se traduce lo que llega por la dirección a un par de
fechas, con su nombre para el encabezado del reporte.

Las semanas son las del calendario ISO 8601, de lunes a domingo, que es como se
trabaja en el Ecuador y como se numeran las semanas en los anexos del SRI. Los
trimestres son naturales (enero–marzo, abril–junio, …), que es lo que pide el
formulario 104 del IVA.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlencode

from factec.sri.fechas import hoy_en_ecuador

__all__ = [
    "PERIODOS",
    "Filtro",
    "ULTIMO_DIA",
    "anterior",
    "fin_de_mes",
    "primer_dia_del_mes",
    "resolver",
    "trimestre_de",
]

#: Los períodos que se ofrecen, en el orden en que salen en el desplegable.
PERIODOS: tuple[tuple[str, str], ...] = (
    ("hoy", "Hoy"),
    ("ayer", "Ayer"),
    ("semana", "Esta semana"),
    ("semana_pasada", "Semana pasada"),
    ("mes", "Este mes"),
    ("mes_pasado", "Mes anterior"),
    ("trimestre", "Este trimestre"),
    ("trimestre_pasado", "Trimestre anterior"),
    ("anio", "Este año"),
    ("anio_pasado", "Año anterior"),
    ("ultimos_30", "Últimos 30 días"),
    ("personalizado", "Rango de fechas"),
    ("todo", "Todo el historial"),
)

#: El período que se usa cuando no se pide ninguno.
DE_OMISION = "mes"

#: El día más antiguo que se pone cuando el período es «todo»: no hay asientos ni
#: comprobantes antes de que existiera el sistema, y así las consultas llevan fecha.
ULTIMO_DIA = date(2000, 1, 1)


@dataclass(frozen=True, slots=True)
class Filtro:
    """El tramo pedido: dos fechas, su nombre y, si toca, la cuenta."""

    clave: str
    desde: date
    hasta: date
    cuenta: Optional[int] = None

    @property
    def etiqueta(self) -> str:
        """El nombre del período, para el encabezado del reporte."""
        return f"{_texto(self.desde, self.hasta)}"

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1

    def como_datos(self) -> dict[str, str]:
        """Lo que vuelve a la dirección para que el filtro siga puesto."""
        return {
            "periodo": self.clave,
            "desde": self.desde.isoformat(),
            "hasta": self.hasta.isoformat(),
        }

    @property
    def consulta(self) -> str:
        """La misma información, ya como cadena para pegar en una dirección."""
        return urlencode(self.como_datos())


def primer_dia_del_mes(cual: date) -> date:
    return date(cual.year, cual.month, 1)


def fin_de_mes(cual: date) -> date:
    return date(cual.year, cual.month, calendar.monthrange(cual.year, cual.month)[1])


def trimestre_de(cual: date) -> tuple[date, date]:
    """El trimestre natural que contiene esa fecha."""
    primero = ((cual.month - 1) // 3) * 3 + 1
    desde = date(cual.year, primero, 1)
    ultimo_mes = primero + 2
    return desde, date(cual.year, ultimo_mes, calendar.monthrange(cual.year, ultimo_mes)[1])


def _semana(cual: date) -> tuple[date, date]:
    """El lunes y el domingo de la semana ISO que contiene esa fecha."""
    lunes = cual - timedelta(days=cual.weekday())
    return lunes, lunes + timedelta(days=6)


def _mas_un_dia(cual: date, dias: int) -> date:
    return cual + timedelta(days=dias)


def _meses_antes(cual: date, cuantos: int = 1) -> date:
    anio, mes = cual.year, cual.month - cuantos
    while mes < 1:
        anio, mes = anio - 1, mes + 12
    return date(anio, mes, 1)


def _texto(desde: date, hasta: date) -> str:
    """«Del 1 al 31 de octubre de 2026», «el 26 de octubre de 2026», «octubre de 2026»."""
    meses = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    if desde == hasta:
        return f"{desde.day} de {meses[desde.month - 1]} de {desde.year}"
    # Un mes completo se nombra por el mes; el resto, por sus días.
    if desde == primer_dia_del_mes(desde) and hasta == fin_de_mes(desde):
        if desde.year == hasta.year:
            return f"{meses[desde.month - 1]} de {desde.year}"
    if desde.year == hasta.year:
        return (
            f"del {desde.day} de {meses[desde.month - 1]} al {hasta.day} de "
            f"{meses[hasta.month - 1]} de {hasta.year}"
        )
    return (
        f"del {desde.day} de {meses[desde.month - 1]} de {desde.year} al "
        f"{hasta.day} de {meses[hasta.month - 1]} de {hasta.year}"
    )


def _fecha(texto: Optional[str]) -> Optional[date]:
    """La fecha de un ``AAAA-MM-DD`` (lo que manda ``<input type="date">``)."""
    if not texto:
        return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        return None


def resolver(datos: dict[str, str], cuenta: Optional[int] = None) -> Filtro:
    """El filtro que pide la dirección, sin fiarse de lo que llegue.

    Si el período no existe o las fechas no se entienden, se vuelve al de omisión:
    un reporte con el mes en curso es mejor que una pantalla de error.
    """
    clave = (datos.get("periodo") or DE_OMISION).strip()
    conocidos = {nombre for nombre, _ in PERIODOS}
    if clave not in conocidos:
        clave = DE_OMISION

    hoy = hoy_en_ecuador()

    if clave == "personalizado":
        desde = _fecha(datos.get("desde"))
        hasta = _fecha(datos.get("hasta"))
        if desde is None and hasta is None:
            clave, desde, hasta = DE_OMISION, None, None
        else:
            desde = desde or hasta
            hasta = hasta or desde
            if desde > hasta:  # se dan la vuelta: se pidió al revés
                desde, hasta = hasta, desde
            return Filtro(clave=clave, desde=desde, hasta=hasta, cuenta=cuenta)

    if clave == "hoy":
        desde = hasta = hoy
    elif clave == "ayer":
        desde = hasta = hoy - timedelta(days=1)
    elif clave == "semana":
        desde, hasta = _semana(hoy)
    elif clave == "semana_pasada":
        desde, hasta = _semana(hoy - timedelta(days=7))
    elif clave == "mes":
        desde, hasta = primer_dia_del_mes(hoy), fin_de_mes(hoy)
    elif clave == "mes_pasado":
        anterior = _meses_antes(hoy)
        desde, hasta = anterior, fin_de_mes(anterior)
    elif clave == "trimestre":
        desde, hasta = trimestre_de(hoy)
    elif clave == "trimestre_pasado":
        desde, hasta = trimestre_de(_mas_un_dia(trimestre_de(hoy)[0], -1))
    elif clave == "anio":
        desde, hasta = date(hoy.year, 1, 1), date(hoy.year, 12, 31)
    elif clave == "anio_pasado":
        desde, hasta = date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31)
    elif clave == "ultimos_30":
        desde, hasta = hoy - timedelta(days=29), hoy
    else:  # «todo»
        desde, hasta = ULTIMO_DIA, hoy

    return Filtro(clave=clave, desde=desde, hasta=hasta, cuenta=cuenta)


def anterior(filtro: Filtro) -> Filtro:
    """El tramo de la misma duración justo antes: sirve para comparar."""
    hasta = filtro.desde - timedelta(days=1)
    desde = hasta - timedelta(days=filtro.dias - 1)
    return Filtro(clave="anterior", desde=desde, hasta=hasta, cuenta=filtro.cuenta)
