"""El acta de cierre de caja, en PDF.

Es el papel que se firma al terminar el turno: quién llevó la caja, cuándo la abrió
y la cerró, cuánto entró y salió, el desglose de los billetes y monedas contados, el
total y la diferencia contra lo esperado.

Lleva el logo del emisor o, si no hay, el de Factiz, igual que los reportes: el acta
se archiva con la contabilidad y tiene que verse como el resto de los papeles.
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
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from factec.django import conf
from reportes.marca import logo_de_los_reportes
from reportes.tabla import dinero

from .models import SesionCaja

__all__ = ["acta"]

MARCA = colors.HexColor("#1570EF")
TINTE = colors.HexColor("#EFF8FF")
LINEA = colors.HexColor("#D6DCE5")
GRIS = colors.HexColor("#667085")


def _estilo(nombre: str, tamano: float, **extra: Any) -> ParagraphStyle:
    base = {"fontName": "Helvetica", "fontSize": tamano, "leading": tamano + 2, "alignment": TA_LEFT}
    base.update(extra)
    return ParagraphStyle(nombre, **base)


_TITULO = _estilo("titulo", 13, fontName="Helvetica-Bold", alignment=TA_CENTER)
_SUBTITULO = _estilo("subtitulo", 8, alignment=TA_CENTER, textColor=GRIS)
_DATO = _estilo("dato", 8)
_DATO_FUERTE = _estilo("dato-fuerte", 9, fontName="Helvetica-Bold")
_DERECHA = _estilo("derecha", 8.5, alignment=TA_RIGHT)
_DERECHA_FUERTE = _estilo("derecha-fuerte", 9, fontName="Helvetica-Bold", alignment=TA_RIGHT)
_NOTA = _estilo("nota", 7, textColor=GRIS)


def _logo(alto: float = 16 * mm) -> Optional[Any]:
    try:
        encontrado = logo_de_los_reportes()
        if not encontrado:
            return None
        lector = ImageReader(BytesIO(encontrado[0]))
        ancho_px, alto_px = lector.getSize()
        if not ancho_px or not alto_px:
            return None
        return Image(BytesIO(encontrado[0]), width=alto * ancho_px / alto_px, height=alto)
    except Exception:  # noqa: BLE001 - un logo roto no puede tumbar el acta
        return None


def _fecha(valor: Any) -> str:
    if not valor:
        return "—"
    local = timezone.localtime(valor) if timezone.is_aware(valor) else valor
    return local.strftime("%d/%m/%Y %H:%M")


def acta(sesion: SesionCaja, movimientos: Any = None) -> bytes:
    """El PDF del acta de cierre de esa sesión."""
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
        title=f"Acta de cierre de caja · {sesion.usuario.get_username()}",
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
            16 * mm, 9 * mm, f"Acta generada por el sistema el {_fecha(timezone.now())}"
        )
        lienzo.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Página {lienzo.getPageNumber()}")
        lienzo.restoreState()

    historia: list[Any] = []

    # --- encabezado con el logo y los datos de la empresa
    datos = [
        Paragraph(empresa, _estilo("empresa", 9, fontName="Helvetica-Bold")),
        Paragraph(f"RUC {ruc}" if ruc else "", _estilo("ruc", 7, textColor=GRIS)),
    ]
    marca = _logo()
    if marca is not None:
        historia.append(
            Table(
                [[marca, datos]],
                colWidths=[45 * mm, documento.width - 45 * mm],
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
    historia.append(Spacer(1, 4 * mm))
    historia.append(Paragraph("ACTA DE CIERRE DE CAJA", _TITULO))
    historia.append(
        Paragraph(
            f"Turno de {sesion.usuario.get_full_name() or sesion.usuario.get_username()}", _SUBTITULO
        )
    )
    historia.append(Spacer(1, 5 * mm))

    # --- los datos del turno
    filas = [
        ["Abierta", _fecha(sesion.abierta_en), "Cerrada", _fecha(sesion.cerrada_en)],
        [
            "Saldo inicial",
            dinero(sesion.saldo_inicial),
            "Efectivo contado",
            dinero(sesion.saldo_declarado),
        ],
        ["Ingresos", dinero(sesion.total_ingresos), "Egresos", dinero(sesion.total_egresos)],
        [
            "Saldo esperado",
            dinero(sesion.saldo_esperado),
            "Diferencia",
            dinero(sesion.diferencia),
        ],
    ]
    tabla_datos = Table(
        [[Paragraph(celda, _DATO) for celda in fila] for fila in filas],
        colWidths=[documento.width * 0.22, documento.width * 0.28, documento.width * 0.24, documento.width * 0.26],
        style=TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.3, LINEA),
                ("BACKGROUND", (0, 0), (0, -1), TINTE),
                ("BACKGROUND", (2, 0), (2, -1), TINTE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
    )
    historia.append(tabla_datos)
    historia.append(Spacer(1, 5 * mm))

    # --- el desglose del efectivo
    historia.append(Paragraph("Desglose del efectivo contado", _estilo("seccion", 9, fontName="Helvetica-Bold")))
    historia.append(Spacer(1, 2 * mm))

    renglones = [["Billetes y monedas", "Cantidad", "Subtotal"]]
    for renglon in sesion.renglones_del_desglose:
        if not renglon["cantidad"]:
            continue
        renglones.append(
            [
                f"$ {dinero(renglon['valor'])}",
                str(renglon["cantidad"]),
                f"$ {dinero(renglon['subtotal'])}",
            ]
        )
    if len(renglones) == 1:
        renglones.append(["Sin desglose registrado", "—", f"$ {dinero(sesion.saldo_declarado)}"])
    renglones.append(["Total contado", "", f"$ {dinero(sesion.saldo_declarado)}"])

    tabla_desglose = Table(
        [[Paragraph(celda, _DATO if indice else _DATO_FUERTE) for celda in fila] for indice, fila in enumerate(renglones)],
        colWidths=[documento.width * 0.5, documento.width * 0.2, documento.width * 0.3],
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), MARCA),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.3, LINEA),
                ("BACKGROUND", (0, -1), (-1, -1), TINTE),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        ),
    )
    historia.append(tabla_desglose)
    historia.append(Spacer(1, 5 * mm))

    # --- los movimientos del turno
    if movimientos is not None:
        lista = list(movimientos[:40])
        if lista:
            historia.append(
                Paragraph("Movimientos del turno", _estilo("seccion2", 9, fontName="Helvetica-Bold"))
            )
            historia.append(Spacer(1, 2 * mm))
            cuerpo = [["Hora", "Tipo", "Concepto", "Referencia", "Importe"]]
            for movimiento in lista:
                cuerpo.append(
                    [
                        _fecha(movimiento.fecha)[-5:],
                        movimiento.get_tipo_display(),
                        movimiento.concepto,
                        movimiento.referencia or "—",
                        f"$ {dinero(movimiento.importe)}",
                    ]
                )
            historia.append(
                Table(
                    [[Paragraph(str(celda), _DATO) for celda in fila] for fila in cuerpo],
                    colWidths=[
                        documento.width * 0.10,
                        documento.width * 0.13,
                        documento.width * 0.42,
                        documento.width * 0.20,
                        documento.width * 0.15,
                    ],
                    repeatRows=1,
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), MARCA),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("GRID", (0, 0), (-1, -1), 0.25, LINEA),
                            ("ALIGN", (4, 0), (4, -1), "RIGHT"),
                            ("TOPPADDING", (0, 0), (-1, -1), 2),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ]
                    ),
                )
            )
            historia.append(Spacer(1, 3 * mm))

    # --- observaciones y firmas
    if sesion.observaciones_cierre:
        historia.append(Paragraph("Observaciones del cierre", _DATO_FUERTE))
        historia.append(Paragraph(sesion.observaciones_cierre, _DATO))
        historia.append(Spacer(1, 4 * mm))

    diferencia = sesion.diferencia
    if diferencia:
        juicio = "FALTANTE" if diferencia < 0 else "SOBRANTE"
        historia.append(
            Paragraph(
                f"<b>El arqueo no cuadra:</b> hay un {juicio} de $ {dinero(abs(diferencia))} "
                "frente al saldo esperado. Queda registrado para revisión.",
                _estilo("aviso", 8, textColor=colors.HexColor("#B42318")),
            )
        )
    else:
        historia.append(
            Paragraph("El arqueo cuadra: lo contado es igual al saldo esperado.", _estilo("cuadra", 8))
        )

    # --- la revisión y, si hay faltante, el vale con el que se cobra
    vales = list(sesion.vales.exclude(estado="anulado")) if sesion.pk else []
    def _nombre(usuario: Any) -> str:
        """El nombre de la persona, y si no lo tiene, el de la cuenta."""
        if usuario is None:
            return "—"
        return usuario.get_full_name().strip() or usuario.get_username()

    if sesion.revision != "sin_revisar":
        quien = _nombre(sesion.revisada_por)
        cuando = (
            timezone.localtime(sesion.revisada_en).strftime("%d/%m/%Y %H:%M")
            if sesion.revisada_en
            else "—"
        )
        historia.append(Spacer(1, 4 * mm))
        historia.append(
            Paragraph(
                f"<b>Revisión:</b> {sesion.get_revision_display()} · {quien} · {cuando}",
                _DATO,
            )
        )
        if sesion.nota_revision:
            historia.append(Paragraph(sesion.nota_revision, _DATO))

    for vale in vales:
        historia.append(Spacer(1, 3 * mm))
        historia.append(
            Paragraph(
                f"<b>Vale {vale.numero}:</b> {vale.get_tipo_display()} de "
                f"$ {dinero(vale.importe)} a {_nombre(vale.responsable)}, "
                f"{vale.get_estado_display().lower()} ({vale.motivo}).",
                _DATO,
            )
        )
    historia.append(Spacer(1, 12 * mm))

    firmas = Table(
        [
            [
                Paragraph("_______________________________<br/>Quien cierra la caja", _estilo("firma", 8, alignment=TA_CENTER)),
                Paragraph("_______________________________<br/>Quien revisa", _estilo("firma", 8, alignment=TA_CENTER)),
            ]
        ],
        colWidths=[documento.width / 2, documento.width / 2],
    )
    historia.append(firmas)

    documento.build(historia, onFirstPage=al_pie, onLaterPages=al_pie)
    return buffer.getvalue()
