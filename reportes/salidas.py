"""Las salidas de un reporte: PDF para archivar e imprimir, Excel para trabajar.

Las dos parten de la misma tabla, así que dicen lo mismo. Las dos llevan el mismo
encabezado: el logo —el del emisor o, si no hay, el de Factiz—, la empresa y su
RUC, el nombre del reporte, el período, quién lo pidió y cuándo se generó. Al pie
van las notas del reporte: de qué norma sale el dato y qué se dejó fuera.

El PDF se arma con ReportLab, que no necesita nada instalado en el sistema, y el
Excel con openpyxl: los dos son bibliotecas de Python que viajan con el proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Any, Optional, Sequence
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ImagenDeExcel
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .marca import logo_de_los_reportes
from .tabla import Tabla, dinero

__all__ = ["Ficha", "excel", "pdf"]

#: Los colores de la casa, los mismos del CSS (``--marca``, ``--marca-osc``).
MARCA = colors.HexColor("#1570EF")
MARCA_OSCURA = colors.HexColor("#175CD3")
TINTE = colors.HexColor("#EFF8FF")
LINEA = colors.HexColor("#D6DCE5")
GRIS = colors.HexColor("#667085")

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


def _imagen(contenido: bytes, alto: float) -> Optional[Any]:
    """La imagen escalada a ese alto, conservando la proporción. ``None`` si no se puede."""
    try:
        lector = ImageReader(BytesIO(contenido))
        ancho_px, alto_px = lector.getSize()
        if not ancho_px or not alto_px:
            return None
        return Image(BytesIO(contenido), width=alto * ancho_px / alto_px, height=alto)
    except Exception:  # noqa: BLE001 - un logo roto no puede tumbar el reporte
        return None


def _logo() -> Optional[tuple[bytes, str]]:
    try:
        return logo_de_los_reportes()
    except Exception:  # noqa: BLE001 - idem
        return None


# --------------------------------------------------------------------- PDF


def _estilo(nombre: str, tamano: float, **extra: Any) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": tamano, "leading": tamano + 1.6}
    base.update(extra)
    return ParagraphStyle(nombre, **base)


_CELDA = _estilo("celda", 6.9)
_CELDA_DERECHA = _estilo("celda-derecha", 6.9, alignment=TA_RIGHT)
_CELDA_CENTRO = _estilo("celda-centro", 6.9, alignment=TA_CENTER)
_CABECERA = _estilo("cabecera", 6.6, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_LEFT)
_CABECERA_DERECHA = _estilo("cabecera-derecha", 6.6, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)
_TOTAL = _estilo("total", 7.2, fontName="Helvetica-Bold")
_TOTAL_DERECHA = _estilo("total-derecha", 7.2, fontName="Helvetica-Bold", alignment=TA_RIGHT)


def _parrafo(texto: Any, estilo: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(texto)), estilo)


def _parrafo_de(columna: Any, valor: Any) -> Paragraph:
    estilo = {
        "derecha": _CELDA_DERECHA,
        "centro": _CELDA_CENTRO,
    }.get(columna.alinear(), _CELDA)
    return _parrafo(columna.formatear(valor), estilo)


def _anchos(tabla: Tabla, disponible: float) -> list[float]:
    """El ancho de cada columna, repartiendo el de la hoja según su peso."""
    pesos = [max(columna.ancho, 0.4) for columna in tabla.columnas]
    total = sum(pesos) or 1
    anchos = [disponible * peso / total for peso in pesos]
    # Ninguna columna baja de 13 mm: si no, el texto se rompe letra a letra.
    minimo = 13 * mm
    if any(ancho < minimo for ancho in anchos):
        justos = sum(1 for ancho in anchos if ancho < minimo)
        holgados = [ancho for ancho in anchos if ancho >= minimo]
        sobra = disponible - minimo * justos
        escala = (sobra / sum(holgados)) if holgados and sobra > 0 else 0
        anchos = [minimo if ancho < minimo else ancho * escala for ancho in anchos]
    return anchos


def pdf(tabla: Tabla, ficha: Ficha) -> bytes:
    """El reporte en PDF, con su encabezado de marca y sus notas al pie."""
    ancha = len(tabla.columnas) > 6
    pagina = landscape(A4) if ancha else A4
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=pagina,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=15 * mm,
        title=f"{ficha.titulo or tabla.titulo} · {ficha.periodo or tabla.subtitulo}",
        author=ficha.empresa or "Factiz",
        subject="Reporte",
        creator="Factiz",
    )

    pie_izquierda = (
        f"Generado por {ficha.usuario or 'el sistema'} el {ficha.cuando}"
        if ficha.usuario
        else f"Generado el {ficha.cuando}"
    )

    def al_pie(lienzo: Any, _documento: Any) -> None:
        lienzo.saveState()
        lienzo.setStrokeColor(LINEA)
        lienzo.setLineWidth(0.4)
        lienzo.line(12 * mm, 11 * mm, pagina[0] - 12 * mm, 11 * mm)
        lienzo.setFont("Helvetica", 6.5)
        lienzo.setFillColor(GRIS)
        lienzo.drawString(12 * mm, 7 * mm, pie_izquierda)
        lienzo.drawRightString(pagina[0] - 12 * mm, 7 * mm, f"Página {lienzo.getPageNumber()}")
        lienzo.restoreState()

    historia: list[Any] = []

    # --- el encabezado: el logo a la izquierda y los datos a la derecha
    datos = [
        _parrafo(ficha.empresa or "Sin configuración del emisor", _estilo("emp", 9, fontName="Helvetica-Bold")),
        _parrafo(f"RUC {ficha.ruc}" if ficha.ruc else "", _estilo("ruc", 7, textColor=GRIS)),
        Spacer(1, 2 * mm),
        _parrafo(tabla.titulo, _estilo("titulo", 12, fontName="Helvetica-Bold", textColor=MARCA_OSCURA)),
        _parrafo(ficha.periodo or tabla.subtitulo, _estilo("periodo", 7.5, textColor=GRIS)),
    ]
    encontrado = _logo()
    # El logo es lo primero que se ve del informe: va con tamaño de sello, no de
    # adorno. La columna que lo lleva crece con él para que no se pegue al texto.
    marca = _imagen(encontrado[0], 18 * mm) if encontrado else None
    if marca is not None:
        historia.append(
            Table(
                [[marca, datos]],
                colWidths=[min(62 * mm, documento.width * 0.34), documento.width - min(62 * mm, documento.width * 0.34)],
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
                    ]
                ),
            )
        )
    else:
        historia.append(Table([[datos]], colWidths=[documento.width], style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)])))
    historia.append(Spacer(1, 3 * mm))

    # --- las cifras destacadas
    if ficha.resumen:
        celdas = [
            [
                Paragraph(f"<font size=6 color='#667085'>{escape(etiqueta.upper())}</font><br/><b>{escape(valor)}</b>", _CELDA)
                for etiqueta, valor in ficha.resumen
            ]
        ]
        historia.append(
            Table(
                celdas,
                colWidths=[documento.width / len(ficha.resumen)] * len(ficha.resumen),
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), TINTE),
                        ("BOX", (0, 0), (-1, -1), 0.4, LINEA),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.white),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 2.4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ]
                ),
            )
        )
        historia.append(Spacer(1, 3 * mm))

    # --- la tabla
    if tabla.vacia:
        historia.append(_parrafo(tabla.sin_datos, _estilo("vacio", 8, textColor=GRIS)))
    else:
        cabecera = [
            _parrafo(
                columna.titulo,
                _CABECERA_DERECHA if columna.alinear() == "derecha" else _CABECERA,
            )
            for columna in tabla.columnas
        ]
        cuerpo = [cabecera]
        for fila in tabla.filas:
            cuerpo.append([_parrafo_de(columna, valor) for columna, valor in zip(tabla.columnas, fila)])
        if tabla.totales is not None:
            cuerpo.append(
                [
                    _parrafo(
                        columna.formatear(valor) if valor not in (None, "") else "",
                        _TOTAL_DERECHA if columna.alinear() == "derecha" else _TOTAL,
                    )
                    for columna, valor in zip(tabla.columnas, tabla.totales)
                ]
            )

        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), MARCA),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINEA),
            ("BOX", (0, 0), (-1, -1), 0.4, LINEA),
        ]
        for indice in range(1, len(cuerpo)):
            if indice % 2 == 0:
                estilo.append(("BACKGROUND", (0, indice), (-1, indice), TINTE))
        if tabla.totales is not None:
            estilo += [
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, MARCA),
                ("BACKGROUND", (0, -1), (-1, -1), TINTE),
            ]
        historia.append(
            Table(
                cuerpo,
                colWidths=_anchos(tabla, documento.width),
                repeatRows=1,
                style=TableStyle(estilo),
            )
        )

    # --- las notas, al pie del reporte
    if ficha.notas:
        notas = [Paragraph(f"— {escape(nota)}", _estilo("nota", 6.4, textColor=GRIS)) for nota in ficha.notas]
        notas.append(
            Paragraph(
                "Documento generado por el sistema. Los valores provienen de los comprobantes "
                "electrónicos autorizados y de los asientos contabilizados.",
                _estilo("nota-final", 6.4, textColor=GRIS),
            )
        )
        historia.append(Spacer(1, 3.5 * mm))
        historia.append(KeepTogether(notas))

    documento.build(historia, onFirstPage=al_pie, onLaterPages=al_pie)
    return buffer.getvalue()


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
    encontrado = _logo()
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
