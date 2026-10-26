"""El vale de caja, en PDF: el papel que se firma.

El vale es lo que justifica sacar efectivo de la caja o cobrarle un faltante a
alguien, así que se imprime: lleva el logo del emisor —o el de Factiz si no hay—,
el número, la fecha, quién responde, cuánto y por qué, y dos firmas.

Comparte el papel del acta de cierre (mismos colores, mismo encabezado): los dos
se archivan juntos.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, Optional

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from factec.django import conf
from reportes.tabla import dinero

from .acta import GRIS, LINEA, MARCA, TINTE, _fecha, _logo

__all__ = ["vale"]


def _estilo(nombre: str, tamano: float, **extra: Any) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": tamano, "leading": tamano + 2, "alignment": TA_LEFT}
    base.update(extra)
    return ParagraphStyle(nombre, **base)


_TITULO = _estilo("titulo", 15, fontName="Helvetica-Bold", alignment=TA_CENTER)
_SUBTITULO = _estilo("subtitulo", 8, alignment=TA_CENTER, textColor=GRIS)
_DATO = _estilo("dato", 9)
_DATO_FUERTE = _estilo("dato-fuerte", 9.5, fontName="Helvetica-Bold")
_NOTA = _estilo("nota", 7, textColor=GRIS)
_IMPORTE = _estilo("importe", 20, fontName="Helvetica-Bold", alignment=TA_RIGHT)


def _nombre(usuario: Any) -> str:
    """El nombre de la persona, y si no lo tiene, el de la cuenta."""
    if usuario is None:
        return "—"
    return usuario.get_full_name().strip() or usuario.get_username()


def vale(el_vale: Any) -> bytes:
    """El PDF de ese vale de caja, listo para imprimir y firmar."""
    emisor = conf.configuracion_activa()
    empresa = getattr(emisor, "razon_social", "") or "Sin configuración del emisor"
    ruc = getattr(emisor, "ruc", "") or ""

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f"Vale de caja {el_vale.numero}",
        author=empresa,
        creator="Factiz",
    )

    def al_pie(lienzo: Any, _documento: Any) -> None:
        lienzo.saveState()
        lienzo.setStrokeColor(LINEA)
        lienzo.setLineWidth(0.4)
        lienzo.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
        lienzo.setFont("Helvetica", 6.5)
        lienzo.setFillColor(GRIS)
        lienzo.drawString(
            16 * mm, 9 * mm, f"Vale generado por el sistema el {_fecha(timezone.now())}"
        )
        lienzo.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Página {lienzo.getPageNumber()}")
        lienzo.restoreState()

    historia: list[Any] = []

    # --- el encabezado: logo y datos de la empresa, como en el acta
    datos = [
        Paragraph(empresa, _estilo("empresa", 9, fontName="Helvetica-Bold")),
        Paragraph(f"RUC {ruc}" if ruc else "", _estilo("ruc", 7, textColor=GRIS)),
    ]
    marca = _logo()
    if marca is not None:
        historia.append(
            Table(
                [[marca, datos]],
                colWidths=[56 * mm, documento.width - 56 * mm],
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ]
                ),
            )
        )
    else:
        historia.append(Table([[datos]], colWidths=[documento.width]))
    historia.append(Spacer(1, 5 * mm))

    historia.append(Paragraph("VALE DE CAJA", _TITULO))
    historia.append(Paragraph(f"N.º {el_vale.numero}", _SUBTITULO))
    historia.append(Spacer(1, 6 * mm))

    # --- cuánto, de qué tipo y en qué estado
    historia.append(
        Table(
            [
                [
                    Paragraph(f"<b>{el_vale.get_tipo_display().upper()}</b>", _DATO),
                    Paragraph(f"$ {dinero(el_vale.importe)}", _IMPORTE),
                ]
            ],
            colWidths=[documento.width * 0.55, documento.width * 0.45],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, -1), TINTE),
                    ("BOX", (0, 0), (-1, -1), 0.6, MARCA),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        )
    )
    historia.append(Spacer(1, 6 * mm))

    # --- los datos del vale
    turno = "—"
    if el_vale.sesion is not None and el_vale.sesion.cerrada_en:
        turno = _fecha(el_vale.sesion.cerrada_en)
    filas = [
        ["Fecha", el_vale.fecha.strftime("%d/%m/%Y"), "Estado", el_vale.get_estado_display()],
        ["Responsable", _nombre(el_vale.responsable), "Caja del turno", turno],
        [
            "Emitido por",
            _nombre(el_vale.creado_por) if el_vale.creado_por else "—",
            "Cobrado el",
            el_vale.cobrado_en.strftime("%d/%m/%Y") if el_vale.cobrado_en else "—",
        ],
    ]
    historia.append(
        Table(
            [[Paragraph(celda, _DATO) for celda in fila] for fila in filas],
            colWidths=[
                documento.width * 0.20,
                documento.width * 0.30,
                documento.width * 0.22,
                documento.width * 0.28,
            ],
            style=TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, LINEA),
                    ("BACKGROUND", (0, 0), (0, -1), TINTE),
                    ("BACKGROUND", (2, 0), (2, -1), TINTE),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        )
    )
    historia.append(Spacer(1, 6 * mm))

    # --- el motivo, que es lo que explica el papel
    historia.append(Paragraph("Motivo", _DATO_FUERTE))
    historia.append(Paragraph(el_vale.motivo or "—", _DATO))
    if el_vale.nota:
        historia.append(Spacer(1, 4 * mm))
        historia.append(Paragraph("Nota", _DATO_FUERTE))
        historia.append(Paragraph(el_vale.nota.replace("\n", "<br/>"), _DATO))

    if el_vale.sesion is not None:
        sesion = el_vale.sesion
        diferencia = sesion.diferencia
        if diferencia < 0:
            cuadre = f"faltante de $ {dinero(abs(diferencia))}"
        elif diferencia > 0:
            cuadre = f"sobrante de $ {dinero(diferencia)}"
        else:
            cuadre = "sin diferencia"
        historia.append(Spacer(1, 4 * mm))
        historia.append(
            Paragraph(
                "Cuadre de ese turno: "
                f"esperado $ {dinero(sesion.saldo_esperado)}, "
                f"contado $ {dinero(sesion.saldo_declarado)}, {cuadre}.",
                _NOTA,
            )
        )

    historia.append(Spacer(1, 4 * mm))
    historia.append(
        Paragraph(
            "Este vale respalda el movimiento de efectivo descrito arriba. Se firma por "
            "duplicado: una copia queda en la caja y la otra en poder del responsable.",
            _NOTA,
        )
    )

    # --- las firmas
    historia.append(Spacer(1, 22 * mm))
    historia.append(
        Table(
            [
                [
                    Paragraph(
                        "_______________________________<br/>Quien autoriza", _estilo("firma", 8, alignment=TA_CENTER)
                    ),
                    Paragraph(
                        f"_______________________________<br/>{_nombre(el_vale.responsable)}",
                        _estilo("firma-responsable", 8, alignment=TA_CENTER),
                    ),
                ]
            ],
            colWidths=[documento.width / 2, documento.width / 2],
        )
    )

    documento.build(historia, onFirstPage=al_pie, onLaterPages=al_pie)
    return buffer.getvalue()
