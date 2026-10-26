"""La tabla que comparten la pantalla, el PDF y el Excel.

Un reporte se arma una sola vez, como una tabla: sus columnas, sus filas y sus
totales. De ahí salen las tres salidas —la que se mira en el navegador, el PDF que
se archiva y el Excel con el que se sigue trabajando—, y así las tres dicen
siempre lo mismo.

Las cifras se escriben al estilo del Ecuador: punto para los miles y coma para los
decimales (``1.234,56``), que es como se leen los estados financieros y los
comprobantes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

__all__ = [
    "CERO",
    "Celda",
    "Columna",
    "Tabla",
    "dinero",
    "entero",
    "fecha_corta",
    "numero",
    "porcentaje",
]

CERO = Decimal("0")

#: Cómo se alinea cada tipo de dato cuando la columna no dice otra cosa.
_ALINEACION = {
    "dinero": "derecha",
    "entero": "derecha",
    "numero": "derecha",
    "porcentaje": "derecha",
    "fecha": "centro",
    "texto": "izquierda",
}


def _decimal(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return CERO
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor))
    except (ArithmeticError, ValueError, TypeError):
        return CERO


def dinero(valor: Any) -> str:
    """``1234.5`` → ``1.234,50``."""
    cuantizado = _decimal(valor).quantize(Decimal("0.01"))
    texto = f"{cuantizado:,.2f}"
    return texto.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def entero(valor: Any) -> str:
    """``1234`` → ``1.234``."""
    return f"{int(_decimal(valor)):,}".replace(",", ".")


def numero(valor: Any) -> str:
    """Un número con decimales solo si los tiene (cantidades, secuenciales)."""
    cuantizado = _decimal(valor)
    if cuantizado == cuantizado.to_integral_value():
        return entero(cuantizado)
    texto = f"{cuantizado.normalize():,f}"
    return texto.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")


def porcentaje(valor: Any) -> str:
    """``15`` → ``15,00 %``."""
    return f"{dinero(valor)} %"


def fecha_corta(valor: Any) -> str:
    """``2026-10-26`` → ``26/10/2026`` (y con la hora, si la trae)."""
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return "" if valor is None else str(valor)


_FORMATOS = {
    "dinero": dinero,
    "entero": entero,
    "numero": numero,
    "porcentaje": porcentaje,
    "fecha": fecha_corta,
    "texto": lambda valor: "" if valor is None else str(valor),
}


@dataclass(frozen=True, slots=True)
class Columna:
    """Una columna del reporte: su título y cómo se lee su dato."""

    titulo: str
    tipo: str = "texto"
    ancho: float = 1.0
    alineacion: str = ""

    def alinear(self) -> str:
        return self.alineacion or _ALINEACION.get(self.tipo, "izquierda")

    def formatear(self, valor: Any) -> str:
        return _FORMATOS.get(self.tipo, _FORMATOS["texto"])(valor)


@dataclass(frozen=True, slots=True)
class Celda:
    """Un dato ya escrito, con su alineación."""

    texto: str
    numerica: bool = False
    alineacion: str = "izquierda"

    @property
    def clase(self) -> str:
        return f"col-{self.alineacion}{' cifra' if self.numerica else ''}"


@dataclass(slots=True)
class Tabla:
    """Un reporte armado: lo que se pinta, lo que se imprime y lo que se exporta."""

    titulo: str
    columnas: Sequence[Columna]
    filas: Sequence[Sequence[Any]] = ()
    subtitulo: str = ""
    #: Cifras destacadas que van sobre la tabla (totales, promedios, variaciones).
    resumen: Sequence[tuple[str, str]] = ()
    #: La fila de totales, alineada con las columnas (``None`` donde no haya).
    totales: Optional[Sequence[Any]] = None
    #: Aclaraciones al pie: de dónde sale el dato y con qué norma se preparó.
    notas: Sequence[str] = ()
    #: La serie que se dibuja como barras sobre la tabla (etiqueta, valor).
    grafico: Sequence[tuple[str, Any]] = ()
    #: Qué decir cuando no hay nada en el período.
    sin_datos: str = "No hay nada que enseñar en este período."

    @property
    def cuantas(self) -> int:
        return len(self.filas)

    @property
    def vacia(self) -> bool:
        return not self.filas

    def renglones(self) -> list[list[Celda]]:
        """Las filas con sus datos ya escritos, para la pantalla."""
        return [
            [
                Celda(columna.formatear(valor), columna.tipo != "texto", columna.alinear())
                for columna, valor in zip(self.columnas, fila)
            ]
            for fila in self.filas
        ]

    def renglon_de_totales(self) -> list[Celda]:
        if self.totales is None:
            return []
        return [
            Celda(columna.formatear(valor), columna.tipo != "texto", columna.alinear())
            for columna, valor in zip(self.columnas, self.totales)
        ]

    def barras(self) -> list[dict[str, Any]]:
        """La serie repartida en barras, con su alto en porcentaje del mayor."""
        valores = [_decimal(valor) for _etiqueta, valor in self.grafico]
        mayor = max(valores, default=CERO)
        return [
            {
                "etiqueta": etiqueta,
                "valor": valor,
                "texto": dinero(valor),
                "alto": float(valor / mayor * 100) if mayor else 0.0,
            }
            for (etiqueta, _valor), valor in zip(self.grafico, valores)
        ]


def sumar(filas: Iterable[Sequence[Any]], posicion: int) -> Decimal:
    """La suma de una columna de la tabla (sin las columnas de texto)."""
    total = CERO
    for fila in filas:
        if posicion < len(fila):
            total += _decimal(fila[posicion])
    return total


def participacion(parte: Any, todo: Any) -> str:
    """El peso de una parte sobre el total, ya escrito (``12,50 %``)."""
    base = _decimal(todo)
    if not base:
        return porcentaje(0)
    return porcentaje(_decimal(parte) / base * 100)


def variacion(ahora: Any, antes: Any) -> str:
    """Cuánto cambió una cifra frente al período anterior, en porcentaje."""
    previo = _decimal(antes)
    if not previo:
        return "—" if not _decimal(ahora) else "nuevo"
    cambio = (_decimal(ahora) - previo) / abs(previo) * 100
    signo = "+" if cambio >= 0 else "−"
    return f"{signo}{porcentaje(abs(cambio))}"
