"""Las salidas de un reporte: PDF para archivar e imprimir, Excel para trabajar.

Las dos parten de la misma tabla, así que dicen lo mismo. Las dos llevan el mismo
encabezado: el logo —el del emisor o, si no hay, el de Factiz—, la empresa y su
RUC, el nombre del reporte, el período, quién lo pidió y cuándo se generó. Al pie
van las notas del reporte: de qué norma sale el dato y qué se dejó fuera.

El PDF sale de **HTML**: la plantilla ``papel/reporte.html`` y la hoja de estilo de
imprenta ``static/css/papel.css``, convertidas con WeasyPrint (ver
``facturero.papel``). El Excel se arma con openpyxl, que —como WeasyPrint— es una
biblioteca de Python que viaja con el proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Any, Optional, Sequence

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ImagenDeExcel
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.utils import timezone

from facturero.papel import logo_en_linea, papel

from .tabla import Tabla, dinero

__all__ = ["Ficha", "excel", "pdf"]

MARCA_EXCEL = "1570EF"
TINTE_EXCEL = "EFF8FF"
LINEA_EXCEL = "D6DCE5"


@dataclass(frozen=True, slots=True)
class Ficha:
    """Lo que va en el encabezado y al pie de cualquier salida."""

    empresa: str = ""
    ruc: str = ""
    titulo: str = ""
    subtitulo: str = ""
    periodo: str = ""
    usuario: str = ""
    generado: datetime = field(default_factory=datetime.now)
    resumen: Sequence[tuple[str, str]] = ()
    notas: Sequence[str] = ()
    archivo: str = "reporte"

    @property
    def cuando(self) -> str:
        return self.generado.strftime("%d/%m/%Y %H:%M")


# ------------------------------------------------------------------- ayudas


def _logo_en_bytes() -> Optional[tuple[bytes, str]]:
    """El logo del emisor o el de Factiz, en bytes: es lo que pide openpyxl."""
    try:
        from .marca import logo_de_los_reportes

        return logo_de_los_reportes()
    except Exception:  # noqa: BLE001 - un logo roto no puede tumbar la hoja
        return None


def _anchos(tabla: Tabla) -> list[float]:
    """El peso de cada columna, en proporción, para repartir el ancho de la hoja.

    En HTML es el navegador —o WeasyPrint— el que reparte: aquí sólo se le dice
    cuánto pesa cada columna, y el mínimo de legibilidad lo pone el CSS.
    """
    pesos = [max(columna.ancho, 0.4) for columna in tabla.columnas]
    total = sum(pesos) or 1
    return [peso / total for peso in pesos]


def pdf(tabla: Tabla, ficha: Ficha) -> bytes:
    """El reporte en PDF, con su encabezado de marca y sus notas al pie.

    Se arma con la plantilla ``papel/reporte.html``: el mismo HTML y el mismo CSS
    de imprenta que el acta de caja y los vales.
    """
    ancha = len(tabla.columnas) > 6
    piezas = _anchos(tabla)
    columnas = [
        {"titulo": columna.titulo, "alinear": columna.alinear(), "parte": round(pieza * 100, 2)}
        for columna, pieza in zip(tabla.columnas, piezas)
    ]
    return papel(
        "papel/reporte.html",
        {
            "ficha": ficha,
            "tabla": tabla,
            "columnas": columnas,
            "totales": tabla.renglon_de_totales() or None,
            "logo": logo_en_linea(),
            "ancha": ancha,
        },
    )


# ------------------------------------------------------------------- Excel


_FORMATOS = {
    "dinero": "#,##0.00",
    "entero": "#,##0",
    "numero": "#,##0.00###",
    "porcentaje": "@",
    "fecha": "DD/MM/YYYY",
}


def _fila_de_cabecera(tabla: Tabla) -> int:
    return 8


def _valor_de_excel(tipo: str, valor: Any) -> Any:
    """El valor que entiende Excel: número para las cifras, fecha para las fechas."""
    if tipo in ("dinero", "entero", "numero"):
        try:
            return float(valor or 0)
        except (TypeError, ValueError):
            return 0.0
    if tipo == "fecha" and isinstance(valor, (date, datetime)):
        # Excel no admite zonas horarias: la fecha va en la hora local del sistema.
        if isinstance(valor, datetime) and timezone.is_aware(valor):
            return timezone.localtime(valor).replace(tzinfo=None)
        return valor
    return "" if valor is None else str(valor)


def _ancho_de_columna(tabla: Tabla, indice: int) -> float:
    columna = tabla.columnas[indice]
    largos = [len(str(fila[indice])) for fila in tabla.filas if indice < len(fila)]
    largo = max([len(columna.titulo)] + largos + [0])
    if columna.tipo in ("dinero", "entero", "numero"):
        largo = max(largo, 12)
    return min(max(largo + 2, 8), 52)


def excel(tabla: Tabla, ficha: Ficha) -> bytes:
    """El reporte en Excel: encabezado de marca, la tabla y sus notas."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = (tabla.titulo or "Reporte")[:31]
    hoja.sheet_view.showGridLines = False

    fino = Side(style="thin", color=LINEA_EXCEL)
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)

    # --- el logo, en la esquina
    encontrado = _logo_en_bytes()
    if encontrado is not None:
        try:
            imagen = ImagenDeExcel(BytesIO(encontrado[0]))
            factor = 72 / max(imagen.height or 1, 1)
            imagen.height = 72
            imagen.width = max(int((imagen.width or 1) * factor), 1)
            hoja.add_image(imagen, "A1")
        except Exception:  # noqa: BLE001 - un logo ilegible no rompe la hoja
            pass

    letra_titulo = Font(name="Calibri", size=14, bold=True, color=MARCA_EXCEL)
    letra_dato = Font(name="Calibri", size=9, color="667085")
    letra_fuerte = Font(name="Calibri", size=10, bold=True, color="101828")

    hoja["C1"] = ficha.empresa or "Sin configuración del emisor"
    hoja["C1"].font = letra_fuerte
    hoja["C2"] = f"RUC {ficha.ruc}" if ficha.ruc else ""
    hoja["C2"].font = letra_dato
    hoja["C3"] = tabla.titulo
    hoja["C3"].font = letra_titulo
    hoja["C4"] = ficha.periodo or tabla.subtitulo
    hoja["C4"].font = letra_dato
    hoja["C5"] = f"Generado por {ficha.usuario or 'el sistema'} el {ficha.cuando}"
    hoja["C5"].font = letra_dato

    # --- las cifras destacadas, una al lado de la otra
    columna = 1
    for etiqueta, valor in ficha.resumen:
        celda_etiqueta = hoja.cell(row=6, column=columna, value=etiqueta.upper())
        celda_etiqueta.font = Font(name="Calibri", size=7, color="667085")
        celda_valor = hoja.cell(row=7, column=columna, value=valor)
        celda_valor.font = Font(name="Calibri", size=10, bold=True, color="101828")
        columna += 2

    # --- la tabla
    fila = _fila_de_cabecera(tabla)
    relleno = PatternFill("solid", start_color=MARCA_EXCEL, end_color=MARCA_EXCEL)
    for indice, columna in enumerate(tabla.columnas, start=1):
        celda = hoja.cell(row=fila, column=indice, value=columna.titulo)
        celda.font = Font(name="Calibri", size=9, bold=True, color="FFFFFF")
        celda.fill = relleno
        celda.border = borde
        celda.alignment = Alignment(
            horizontal="right" if columna.alinear() == "derecha" else "left",
            vertical="center",
            wrap_text=True,
        )
        hoja.column_dimensions[get_column_letter(indice)].width = _ancho_de_columna(tabla, indice - 1)

    tintado = PatternFill("solid", start_color=TINTE_EXCEL, end_color=TINTE_EXCEL)
    for posicion, datos in enumerate(tabla.filas, start=fila + 1):
        for indice, (columna, valor) in enumerate(zip(tabla.columnas, datos), start=1):
            celda = hoja.cell(row=posicion, column=indice)
            celda.value = _valor_de_excel(columna.tipo, valor)
            celda.number_format = _FORMATOS.get(columna.tipo, "General")
            celda.font = Font(name="Calibri", size=9)
            celda.border = borde
            celda.alignment = Alignment(
                horizontal="right" if columna.alinear() == "derecha" else "left",
                vertical="center",
                wrap_text=columna.tipo == "texto",
            )
            if (posicion - fila) % 2 == 0:
                celda.fill = tintado

    ultima = fila + len(tabla.filas)
    if tabla.totales is not None:
        ultima += 1
        for indice, (columna, valor) in enumerate(zip(tabla.columnas, tabla.totales), start=1):
            celda = hoja.cell(row=ultima, column=indice)
            if valor is None:
                continue
            celda.value = _valor_de_excel(columna.tipo, valor)
            celda.number_format = _FORMATOS.get(columna.tipo, "General")
            celda.font = Font(name="Calibri", size=9, bold=True, color=MARCA_EXCEL)
            celda.fill = tintado
            celda.border = Border(left=fino, right=fino, bottom=fino, top=Side(style="medium", color=MARCA_EXCEL))
            celda.alignment = Alignment(
                horizontal="right" if columna.alinear() == "derecha" else "left",
                vertical="center",
            )

    if tabla.filas:
        hoja.auto_filter.ref = f"A{fila}:{get_column_letter(len(tabla.columnas))}{fila + len(tabla.filas)}"
    hoja.freeze_panes = hoja.cell(row=fila + 1, column=1)

    # --- las notas, debajo
    fila_notas = ultima + 2
    for nota in list(ficha.notas) + [
        "Documento generado por el sistema a partir de los comprobantes autorizados y de "
        "los asientos contabilizados."
    ]:
        celda = hoja.cell(row=fila_notas, column=1, value=f"— {nota}")
        celda.font = Font(name="Calibri", size=8, italic=True, color="667085")
        celda.alignment = Alignment(wrap_text=True, vertical="top")
        hoja.merge_cells(
            start_row=fila_notas,
            start_column=1,
            end_row=fila_notas,
            end_column=max(len(tabla.columnas), 4),
        )
        hoja.row_dimensions[fila_notas].height = 26
        fila_notas += 1

    libro.properties.title = tabla.titulo
    libro.properties.subject = ficha.periodo or tabla.subtitulo
    libro.properties.creator = "Factiz"
    libro.properties.company = ficha.empresa
    buffer = BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def nombre_de_archivo(ficha: Ficha, tabla: Tabla, extension: str) -> str:
    """El nombre con el que se descarga: sin acentos ni espacios."""
    cuando = ficha.periodo or f"{ficha.generado:%Y%m%d}"
    base = f"{ficha.archivo or tabla.titulo}-{cuando}"
    limpio = "".join(
        letra if letra.isalnum() or letra in "-_" else "_" for letra in base
    )
    return f"{limpio.strip('_')}.{extension}"
