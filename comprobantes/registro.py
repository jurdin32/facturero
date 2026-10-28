"""Los comprobantes electrónicos que no son la factura, descritos una vez.

Desde fuera todos son lo mismo: una lista, un formulario, una ficha con lo que
respondió el SRI y un RIDE para imprimir. Lo que cambia es qué se llena y qué se
enseña, y eso es lo que dice este registro. Las vistas y las plantillas son las
mismas para todos: para añadir un comprobante —o cambiarle un texto— se toca aquí
y su formulario, nada más.

De la factura se encarga la app ``facturacion``, que tiene su propia pantalla
(tablero, buscador de productos, resumen en vivo). Aquí van los cinco restantes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from factec.django.documentos import (
    GuiaDestinatario,
    GuiaRemision,
    LiquidacionCompra,
    NotaCredito,
    NotaDebito,
    Retencion,
    RetencionDocSustento,
)

from . import forms

__all__ = ["DOCUMENTOS", "POR_CLAVE", "Documento", "documento_de", "todos"]


def al_autorizar_nota_credito(nota: Any, usuario: Any = None) -> Any:
    """Lo que devuelve una nota de crédito vuelve al inventario.

    La factura sacó esa mercadería del almacén; si el cliente la devuelve, entra otra
    vez, y queda escrito en el libro con la nota apuntada. El importe va dentro del
    módulo del inventario para no atar los dos desde el arranque.
    """
    from inventario.servicios import devolver_de_la_nota_credito

    return devolver_de_la_nota_credito(nota, usuario=usuario)


@dataclass(frozen=True)
class Documento:
    """Un comprobante electrónico, como lo ve la pantalla."""

    #: Lo que va en la dirección: ``/comprobantes/notas-credito/``.
    clave: str
    #: El modelo del paquete que hay detrás.
    modelo: Any
    #: Cómo se llama, en singular y en plural.
    titulo: str
    plural: str
    #: El icono de la casa, sin el prefijo (``mif-``): lo pone la plantilla.
    icono: str
    #: Una línea de ayuda, para cuando la lista está vacía.
    ayuda: str
    #: Cómo se llama el botón de crear: «Nueva nota de crédito».
    nuevo: str
    #: El formulario de la cabecera.
    formulario: Any
    #: La propiedad que dice el nombre de la otra parte (el receptor, el proveedor…).
    contraparte: Callable[[Any], str]
    #: El nombre del campo de la otra parte, para traerlo de una vez en la lista.
    campo_contraparte: str = ""
    #: Lo que se cobra o se retiene, si el comprobante lo tiene.
    importe: Optional[Callable[[Any], Decimal]] = None
    #: El formset de las líneas, si el comprobante lleva (la nota de débito, no).
    lineas: Optional[Any] = None
    #: Cómo se llama ese bloque en la pantalla («Qué se devuelve»).
    lineas_titulo: str = "Líneas"
    #: El formset y el bloque de una fila hija que va dentro de la cabecera
    #: (el destinatario de la guía, el documento sustento de la retención).
    hijo: Optional[Any] = None
    hijo_titulo: str = ""
    #: El modelo del hijo y el campo que lo cuelga de la cabecera.
    hijo_modelo: Any = None
    hijo_campo: str = ""
    #: Un segundo bloque de filas colgadas del hijo (la retención lleva dos:
    #: los impuestos del documento y lo que se retiene).
    lineas2: Optional[Any] = None
    lineas2_titulo: str = ""
    #: Cuando la cabecera se repite (varios destinatarios, varios documentos del
    #: proveedor), cada una con sus filas dentro: (nombre, formset, título).
    hijos_filas: tuple[tuple[str, Any, str], ...] = ()
    #: Los campos de esa cabecera que se ven en su fila de la tabla, en orden. Lo demás
    #: se escribe en la ventana que abre la fila.
    resumen: tuple[str, ...] = ()
    #: Cómo se llaman en esa tabla los campos del resumen y las tablas de dentro, cuando
    #: el nombre largo no cabe. Lo que no esté aquí se queda con su etiqueta.
    titulos_cortos: dict[str, str] = field(default_factory=dict)
    #: Qué hacer cuando el SRI lo autoriza (devolver el stock de una devolución…).
    al_autorizar: Optional[Callable[[Any, Any], Any]] = None
    #: Los comprobantes que se pueden modificar (solo nota de crédito y de débito).
    modificado: Optional[dict[str, str]] = None
    #: La plantilla que pinta el cuerpo del RIDE (las líneas, los motivos…).
    cuerpo: str = ""

    @property
    def opcion(self) -> str:
        """La opción del menú que gobierna este comprobante.

        La dirección usa guiones (``notas-credito``) y las opciones, guiones bajos:
        la plantilla pregunta por los permisos con esta y no con ``clave``, que no
        es ninguna opción y dejaba el botón «Nuevo» a merced de un error de lectura.
        """
        return self.clave.replace("-", "_")


#: Los seis comprobantes del SRI, por su tipo. El que no lleva líneas no las pide.
DOCUMENTOS: tuple[Documento, ...] = (
    Documento(
        clave="notas-credito",
        modelo=NotaCredito,
        titulo="Nota de crédito",
        plural="Notas de crédito",
        icono="minus",
        ayuda="Anula o corrige una factura ya emitida: devoluciones, descuentos, errores.",
        nuevo="Nueva nota de crédito",
        formulario=forms.FormularioNotaCredito,
        contraparte=lambda nota: nota.receptor.razon_social,
        campo_contraparte="receptor",
        al_autorizar=al_autorizar_nota_credito,
        importe=lambda nota: nota.total,
        lineas=forms.LineasDeNotaCredito,
        lineas_titulo="Qué se devuelve",
        modificado=forms.DOCUMENTOS_QUE_MODIFICA,
        cuerpo="comprobantes/cuerpos/lineas.html",
    ),
    Documento(
        clave="notas-debito",
        modelo=NotaDebito,
        titulo="Nota de débito",
        plural="Notas de débito",
        icono="plus",
        ayuda="Cobra valores que no iban en la factura: intereses, gastos, ajustes.",
        nuevo="Nueva nota de débito",
        formulario=forms.FormularioNotaDebito,
        contraparte=lambda nota: nota.receptor.razon_social,
        campo_contraparte="receptor",
        importe=lambda nota: nota.total,
        lineas=forms.MotivosDeNotaDebito,
        lineas_titulo="Qué se cobra",
        modificado=forms.DOCUMENTOS_QUE_MODIFICA,
        cuerpo="comprobantes/cuerpos/motivos.html",
    ),
    Documento(
        clave="liquidaciones-compra",
        modelo=LiquidacionCompra,
        titulo="Liquidación de compra",
        plural="Liquidaciones de compra",
        icono="cart-product",
        ayuda="Compra a quien no está obligado a facturar: le entrega usted el comprobante.",
        nuevo="Nueva liquidación de compra",
        formulario=forms.FormularioLiquidacionCompra,
        contraparte=lambda liquidacion: liquidacion.proveedor.razon_social,
        campo_contraparte="proveedor",
        importe=lambda liquidacion: liquidacion.total,
        lineas=forms.LineasDeLiquidacionCompra,
        lineas_titulo="Qué se compra",
        cuerpo="comprobantes/cuerpos/lineas.html",
    ),
    Documento(
        clave="guias-remision",
        modelo=GuiaRemision,
        titulo="Guía de remisión",
        plural="Guías de remisión",
        icono="truck",
        ayuda="Para transportar bienes: de dónde salen, quién los lleva y a quién.",
        nuevo="Nueva guía de remisión",
        formulario=forms.FormularioGuiaRemision,
        contraparte=lambda guia: (
            guia.destinatarios.first().razon_social if guia.pk else ""
        ),
        campo_contraparte="",
        importe=None,
        hijo=forms.DestinatarioDeGuia,
        hijo_titulo="A quién se le entrega",
        hijo_modelo=GuiaDestinatario,
        hijo_campo="guia",
        hijos_filas=(("bienes", forms.BienesDeGuia, "Qué se transporta"),),
        resumen=("razon_social", "identificacion", "motivo_traslado"),
        titulos_cortos={"bienes": "Bienes"},
        cuerpo="comprobantes/cuerpos/bienes.html",
    ),
    Documento(
        clave="retenciones",
        modelo=Retencion,
        titulo="Comprobante de retención",
        plural="Comprobantes de retención",
        icono="percent",
        ayuda="Retiene IVA o renta al proveedor; solo si está inscrito como agente.",
        nuevo="Nuevo comprobante de retención",
        formulario=forms.FormularioRetencion,
        contraparte=lambda retencion: retencion.sujeto_retenido.razon_social,
        campo_contraparte="sujeto_retenido",
        importe=lambda retencion: retencion.total_retenido,
        hijo=forms.DocumentoSustento,
        hijo_titulo="Documento que se retiene",
        hijo_modelo=RetencionDocSustento,
        hijo_campo="retencion",
        hijos_filas=(
            ("impuestos", forms.ImpuestosDeRetencion, "Impuestos del documento"),
            ("retenciones", forms.RetencionesDeSustento, "Lo que se retiene"),
        ),
        resumen=("num_doc_sustento", "fecha_emision", "importe_total"),
        titulos_cortos={
            "num_doc_sustento": "Documento",
            "fecha_emision": "Fecha",
            "importe_total": "Total",
            "impuestos": "Impuestos",
            "retenciones": "Retención",
        },
        cuerpo="comprobantes/cuerpos/retencion.html",
    ),
)

#: Los documentos por su clave, para resolver la dirección.
POR_CLAVE: dict[str, Documento] = {documento.clave: documento for documento in DOCUMENTOS}


def todos() -> tuple[Documento, ...]:
    """Los comprobantes, en el orden del menú."""
    return DOCUMENTOS


def documento_de(clave: str) -> Documento:
    """El comprobante de esa clave. Lanza ``KeyError`` si no existe."""
    return POR_CLAVE[clave]
