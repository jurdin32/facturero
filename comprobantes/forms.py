"""Los formularios de los comprobantes electrónicos que no son la factura.

El paquete trae los modelos y el XML; aquí se dice qué se pide en pantalla y cómo se
escribe. Cada comprobante tiene su formulario de cabecera y, si lleva filas —las
líneas, los motivos, los bienes, los impuestos—, un formset que se pinta como una
tabla y se guarda con la cabecera.

Los que van dentro de otro (el destinatario de la guía, el documento que sustenta una
retención) se piden en el mismo formulario: una guía se entrega a un destinatario y
una retención se hace sobre un documento, que es el caso de todos los días. Para
varios destinatarios o varias facturas en una misma retención está el admin del
paquete, que los pide anidados.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.forms import inlineformset_factory
from django.urls import reverse

from factec.django.documentos import (
    Conductor,
    GuiaDestinatario,
    GuiaDetalle,
    GuiaRemision,
    LiquidacionCompra,
    LiquidacionCompraDetalle,
    LineaDocumento,
    NotaCredito,
    NotaCreditoDetalle,
    NotaDebito,
    NotaDebitoMotivo,
    Retencion,
    RetencionDocSustento,
    RetencionDocSustentoImpuesto,
    RetencionImpuesto,
    Vehiculo,
)
from factec.django.forms import LineaDocumentoForm
from factec.django.models import TipoComprobante

from catalogos.models import opciones_de_retencion, porcentajes_de_retencion
from facturero.controles import CampoImporte, caja, de_fecha, desplegable, numero

__all__ = [
    "DOCUMENTOS_QUE_MODIFICA",
    "BienesDeGuia",
    "DestinatarioDeGuia",
    "DocumentoSustento",
    "FormularioGuiaRemision",
    "FormularioLiquidacionCompra",
    "FormularioNotaCredito",
    "FormularioNotaDebito",
    "FormularioRetencion",
    "ImpuestosDeRetencion",
    "LineasDeLiquidacionCompra",
    "LineasDeNotaCredito",
    "MotivosDeNotaDebito",
    "RetencionesDeSustento",
    "SelectDeRetencion",
]

#: Los comprobantes que puede modificar una nota de crédito o de débito.
DOCUMENTOS_QUE_MODIFICA = {
    TipoComprobante.FACTURA.value: "Factura",
    TipoComprobante.LIQUIDACION_COMPRA.value: "Liquidación de compra",
    TipoComprobante.NOTA_DEBITO.value: "Nota de débito",
    TipoComprobante.GUIA_REMISION.value: "Guía de remisión",
    TipoComprobante.COMPROBANTE_RETENCION.value: "Comprobante de retención",
}

#: Lo que se ve de una fila: la descripción y las cifras; lo demás viaja oculto.
_OCULTOS = (
    "producto",
    "codigo_principal",
    "codigo_auxiliar",
    "unidad_medida",
    "codigo_porcentaje_iva",
    "datos_adicionales",
)


def _numero(campo: forms.Field) -> forms.Field:
    """Deja un campo de números listo para el CSS propio (texto y teclado decimal)."""
    campo.localize = False
    if hasattr(campo.widget, "input_type"):
        campo.widget.input_type = "text"
    campo.widget.attrs.update(numero())
    return campo


def _buscador() -> forms.Widget:
    """La otra parte se busca, no se despliega: puede haber cientos de clientes.

    El campo de verdad va oculto y en su lugar se pinta la barra del buscador (ver
    ``comprobantes.js``): la marca dice a la plantilla que ese campo es de esos.
    """
    return forms.HiddenInput(attrs={"buscador": "clientes"})


#: El ancho de cada columna de las tablas de filas, con los nombres del CSS de la casa.
COLUMNAS = {
    "descripcion": "col-descripcion",
    "razon": "col-descripcion",
    "cantidad": "col-cantidad",
    "codigo_porcentaje": "col-cantidad",
    "precio_unitario": "col-precio",
    "base_imponible": "col-precio",
    "descuento": "col-descuento",
    "porcentaje_retener": "col-descuento",
    "valor": "col-importe",
    "valor_retenido": "col-importe",
    "codigo": "col-codigo",
    "codigo_principal": "col-codigo",
    "codigo_retencion": "col-retencion",
}


def _columnas(formulario: Any) -> None:
    """Le pone a cada campo la clase de su columna, para que la tabla cuadre."""
    for nombre, clase in COLUMNAS.items():
        if nombre in formulario.fields:
            formulario.fields[nombre].widget.attrs["columna"] = clase


class SelectDeRetencion(forms.Select):
    """La lista de códigos del SRI, con el porcentaje y el impuesto de cada uno.

    Cada opción lleva su porcentaje y su impuesto en un ``data-*``: al elegir el
    concepto se ponen solos, que es lo que se espera de una tabla oficial (ver
    ``comprobantes.js``).
    """

    def __init__(
        self,
        *args: Any,
        datos: dict[str, tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.datos = datos or {}

    def create_option(  # type: ignore[override]
        self, name: str, value: Any, label: Any, selected: Any, index: int,
        subindex: Any = None, attrs: Any = None,
    ) -> dict[str, Any]:
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        porcentaje, impuesto = self.datos.get(str(value), ("", ""))
        opcion["attrs"]["data-porcentaje"] = porcentaje
        opcion["attrs"]["data-impuesto"] = impuesto
        return opcion


# ------------------------------------------------------------------ cabeceras


class _Cabecera(forms.ModelForm):
    """Lo que comparten las cinco cabeceras: las fechas y los campos de texto.

    Se piden con los controles de Metro y con las etiquetas de la casa; cada
    comprobante decide después qué campos enseña.
    """

    class Meta:
        abstract = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if isinstance(campo.widget, forms.HiddenInput):
                continue
            if isinstance(campo, forms.ModelChoiceField):
                campo.widget.attrs.update(desplegable())
                campo.widget.attrs["class"] = "campo-desplegable"
                continue
            if isinstance(campo, forms.DateField):
                de_fecha(campo)
                continue
            if isinstance(campo, forms.DecimalField):
                _numero(campo)
                continue
            if isinstance(campo.widget, forms.Textarea):
                campo.widget.attrs.update(caja(clase="campo-texto"))
                continue
            campo.widget.attrs.update(caja())
        # Los importes se escriben como se dicen aquí: 1.234,56.
        for nombre in self.IMPORTES:
            if nombre in self.fields:
                self.fields[nombre] = CampoImporte(
                    required=self.fields[nombre].required,
                    min_value=Decimal("0"),
                    label=self.fields[nombre].label,
                )
                _numero(self.fields[nombre])
        self.fields["fecha_emision"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]

    #: Los campos que, siendo decimales, se escriben a mano (los demás son del SRI).
    IMPORTES: tuple[str, ...] = ()


class FormularioNotaCredito(_Cabecera):
    """La nota de crédito: a quién, por qué y qué documento corrige."""

    IMPORTES = ("plazo",)

    class Meta(_Cabecera.Meta):
        model = NotaCredito
        fields = [
            "receptor", "fecha_emision", "motivo", "cod_doc_modificado",
            "num_doc_modificado", "fecha_emision_doc_sustento", "observaciones",
            "informacion_adicional",
        ]
        labels = {
            "receptor": "Cliente",
            "motivo": "Motivo de la nota",
            "cod_doc_modificado": "Documento que modifica",
            "num_doc_modificado": "Número del documento",
            "fecha_emision_doc_sustento": "Fecha de ese documento",
        }
        widgets = {
            "receptor": _buscador(),
            # El comprobante que modifica se elige en su buscador: se ve en la barra y
            # viaja oculto, para no pedir lo mismo tres veces.
            "cod_doc_modificado": forms.HiddenInput(),
            "num_doc_modificado": forms.HiddenInput(),
            "fecha_emision_doc_sustento": forms.HiddenInput(),
            "motivo": forms.TextInput(
                attrs=caja(icono="pencil", placeholder="Devolución, descuento, error…")
            ),
        }


class FormularioNotaDebito(_Cabecera):
    """La nota de débito: a quién se le cobra y qué documento se completa."""

    IMPORTES = ("plazo", "base_imponible")

    class Meta(_Cabecera.Meta):
        model = NotaDebito
        fields = [
            "receptor", "fecha_emision", "cod_doc_modificado", "num_doc_modificado",
            "fecha_emision_doc_sustento", "codigo_porcentaje_iva", "forma_pago",
            "plazo", "unidad_tiempo", "base_imponible", "observaciones",
            "informacion_adicional",
        ]
        labels = {
            "receptor": "Cliente",
            "cod_doc_modificado": "Documento que modifica",
            "num_doc_modificado": "Número del documento",
            "fecha_emision_doc_sustento": "Fecha de ese documento",
            "base_imponible": "Base imponible (si no, la suma de los motivos)",
        }
        widgets = {
            "receptor": _buscador(),
            # El comprobante que modifica se elige en su buscador, como en la nota de crédito.
            "cod_doc_modificado": forms.HiddenInput(),
            "num_doc_modificado": forms.HiddenInput(),
            "fecha_emision_doc_sustento": forms.HiddenInput(),
        }


class FormularioLiquidacionCompra(_Cabecera):
    """La liquidación de compra: a quién se le compra y cómo se paga."""

    IMPORTES = ("plazo",)

    class Meta(_Cabecera.Meta):
        model = LiquidacionCompra
        fields = [
            "proveedor", "fecha_emision", "forma_pago", "plazo", "unidad_tiempo",
            "correo", "observaciones", "informacion_adicional",
        ]
        labels = {"proveedor": "Proveedor", "correo": "Correo del proveedor"}
        widgets = {
            "proveedor": _buscador(),
            "correo": forms.EmailInput(attrs=caja(icono="mail")),
        }


class FormularioGuiaRemision(_Cabecera):
    """La guía de remisión: de dónde sale, quién la lleva y cuándo."""

    #: El conductor y el vehículo se eligen de sus listas: al guardar se copian al
    #: comprobante, que es lo que viaja al SRI (razón social, RUC y placa).
    conductor = forms.ModelChoiceField(
        queryset=Conductor.objects.filter(activo=True),
        label="Quién transporta",
        required=False,
        help_text="Si transporta usted mismo, dése de alta como conductor con su RUC.",
    )
    vehiculo = forms.ModelChoiceField(
        queryset=Vehiculo.objects.filter(activo=True),
        label="Vehículo",
        required=False,
    )

    class Meta(_Cabecera.Meta):
        model = GuiaRemision
        fields = [
            "fecha_emision", "dir_partida", "razon_social_transportista",
            "ruc_transportista", "tipo_identificacion_transportista", "placa",
            "fecha_ini_transporte", "fecha_fin_transporte", "observaciones",
            "informacion_adicional",
        ]
        labels = {
            "dir_partida": "Dirección de partida",
            "razon_social_transportista": "Quién transporta",
            "ruc_transportista": "RUC del transportista",
            "placa": "Placa del vehículo",
            "fecha_ini_transporte": "Inicio del transporte",
            "fecha_fin_transporte": "Fin del transporte",
        }
        widgets = {
            "dir_partida": forms.TextInput(attrs=caja(icono="location")),
            # Lo que sale del conductor y del vehículo elegidos: no se escribe a mano.
            "razon_social_transportista": forms.HiddenInput(),
            "ruc_transportista": forms.HiddenInput(),
            "tipo_identificacion_transportista": forms.HiddenInput(),
            "placa": forms.HiddenInput(),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for nombre in (
            "razon_social_transportista",
            "ruc_transportista",
            "tipo_identificacion_transportista",
            "placa",
        ):
            self.fields[nombre].required = False
        # Al volver a una guía guardada se deja elegido lo que tenía.
        if self.instance.pk:
            self.fields["conductor"].initial = Conductor.objects.filter(
                identificacion=self.instance.ruc_transportista
            ).first()
            self.fields["vehiculo"].initial = Vehiculo.objects.filter(
                placa=self.instance.placa
            ).first()

    def save(self, commit: bool = True) -> Any:
        """Lo elegido (conductor y vehículo) es lo que se guarda en el comprobante."""
        guia = super().save(commit=False)
        conductor = self.cleaned_data.get("conductor")
        if conductor is not None:
            guia.razon_social_transportista = conductor.razon_social
            guia.ruc_transportista = conductor.identificacion
            guia.tipo_identificacion_transportista = conductor.tipo_identificacion
        vehiculo = self.cleaned_data.get("vehiculo")
        if vehiculo is not None:
            guia.placa = vehiculo.placa
        if commit:
            guia.save()
        return guia


class FormularioRetencion(_Cabecera):
    """La retención: a quién se le retiene y de qué mes."""

    class Meta(_Cabecera.Meta):
        model = Retencion
        fields = [
            "sujeto_retenido", "fecha_emision", "periodo_fiscal", "parte_rel",
            "tipo_sujeto_retenido", "observaciones", "informacion_adicional",
        ]
        labels = {
            "sujeto_retenido": "Proveedor",
            "periodo_fiscal": "Mes que se retiene",
            "parte_rel": "¿Es parte relacionada?",
            "tipo_sujeto_retenido": "Tipo de sujeto",
        }
        widgets = {"sujeto_retenido": _buscador()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # El SRI solo quiere este dato cuando el retenido se identifica como del
        # exterior; con RUC, cédula o pasaporte lo devuelve por «error en diferencias».
        self.fields["tipo_sujeto_retenido"].help_text = (
            "Solo cuando el proveedor se identifica como del exterior. "
            "Con RUC o cédula el SRI no lo admite y devuelve el comprobante."
        )


# ------------------------------------------------------- hijos de la cabecera


class _FechasDelNavegador(forms.ModelForm):
    """Las fechas se piden con el campo de fecha del navegador y no con una caja de
    texto: una fecha escrita a mano se escribe mal, y el calendario la dice.

    El campo de fecha de Django sale como caja de texto, así que se le pone el tipo
    a mano, igual que en las cabeceras.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo, forms.DateField) and not isinstance(
                campo.widget, forms.HiddenInput
            ):
                de_fecha(campo)


class DestinatarioDeGuia(_FechasDelNavegador):
    """A quién se le entrega lo que va en la guía."""

    class Meta:
        model = GuiaDestinatario
        fields = [
            "razon_social", "identificacion", "tipo_identificacion", "direccion",
            "motivo_traslado", "ruta", "cod_estab_destino", "cod_doc_sustento",
            "num_doc_sustento", "fecha_emision_doc_sustento",
        ]
        labels = {
            "razon_social": "A quién se le entrega",
            "identificacion": "Identificación",
            "direccion": "Dirección de entrega",
            "motivo_traslado": "Motivo del traslado",
            "ruta": "Ruta",
            "cod_estab_destino": "Código del establecimiento destino",
            "cod_doc_sustento": "Documento que ampara el traslado",
            "num_doc_sustento": "Número de ese documento",
            "fecha_emision_doc_sustento": "Fecha de ese documento",
        }
        widgets = {
            "razon_social": _buscador(),
            "identificacion": forms.HiddenInput(),
            "tipo_identificacion": forms.HiddenInput(),
            # La dirección se pide a la vista: muchos clientes no la traen y el SRI la
            # quiere. El buscador la llena cuando el cliente la tiene.
            "direccion": forms.TextInput(
                attrs=caja(icono="location", placeholder="Calle y número, ciudad")
            ),
            "num_doc_sustento": forms.TextInput(
                attrs=caja(icono="barcode", clase="campo-codigo",
                           placeholder="001-001-000000001")
            ),
            "ruta": forms.TextInput(attrs=caja(icono="map")),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for nombre in ("motivo_traslado", "cod_doc_sustento"):
            self.fields[nombre].widget.attrs.update(desplegable())
        # Quién recibe se elige con el buscador de clientes: de él salen el nombre, la
        # identificación, el tipo y la dirección, así que se llena todo de una vez.
        self.fields["razon_social"].widget.attrs["llena"] = (
            "razon_social,identificacion,tipo_identificacion,direccion"
        )


class DocumentoSustento(_FechasDelNavegador):
    """La factura del proveedor sobre la que se retiene."""

    class Meta:
        model = RetencionDocSustento
        fields = [
            "cod_sustento", "cod_doc_sustento", "num_doc_sustento", "fecha_emision",
            "num_aut_doc_sustento", "total_sin_impuestos", "importe_total",
            "pago_loc_ext",
        ]
        labels = {
            "cod_sustento": "Concepto del gasto",
            "cod_doc_sustento": "Tipo de documento",
            "num_doc_sustento": "Número del documento",
            "fecha_emision": "Fecha de emisión",
            "num_aut_doc_sustento": "Número de autorización o clave de acceso",
            "total_sin_impuestos": "Total sin impuestos",
            "importe_total": "Total del documento",
            "pago_loc_ext": "El pago es",
        }
        widgets = {
            "num_doc_sustento": forms.TextInput(
                attrs=caja(icono="barcode", clase="campo-codigo",
                           placeholder="001001000000123")
            ),
            "num_aut_doc_sustento": forms.TextInput(attrs=caja(icono="key", clase="campo-codigo")),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for nombre in ("cod_sustento", "cod_doc_sustento", "pago_loc_ext"):
            self.fields[nombre].widget.attrs.update(desplegable())
        for nombre in ("total_sin_impuestos", "importe_total"):
            _numero(self.fields[nombre])


# ------------------------------------------------------------------- líneas


class LineaDeComprobante(LineaDocumentoForm):
    """Una línea de comprobante: qué se pone, cuánto y a cómo.

    Es la línea del paquete, con la cantidad y el precio escritos como se dicen aquí.
    """

    cantidad = CampoImporte(min_value=Decimal("0.000001"), initial=Decimal("1"), label="Cantidad")
    precio_unitario = CampoImporte(min_value=Decimal("0"), required=False, label="Precio")
    descuento = CampoImporte(min_value=Decimal("0"), required=False, label="Descuento")

    class Meta(LineaDocumentoForm.Meta):
        # «producto» no está aquí: cada tipo de línea lo cuelga de su propia tabla, y lo
        # añaden las dos líneas de abajo.
        fields = [
            "codigo_principal", "descripcion", "unidad_medida", "cantidad",
            "precio_unitario", "descuento", "codigo_porcentaje_iva", "codigo_auxiliar",
            "datos_adicionales",
        ]
        widgets = {
            nombre: forms.HiddenInput() for nombre in _OCULTOS if nombre != "producto"
        }
        widgets["descripcion"] = forms.TextInput(
            attrs={"placeholder": "Qué se factura", "autocomplete": "off"}
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for nombre in ("cantidad", "precio_unitario", "descuento"):
            _numero(self.fields[nombre])
        _columnas(self)
        # La línea viene del comprobante: se mira y se quita, pero no se escribe encima.
        # La cantidad sí se cambia: es lo que se devuelve, no lo que se vendió.
        for nombre in ("descripcion", "precio_unitario", "descuento"):
            campo = self.fields[nombre]
            campo.widget.attrs["readonly"] = True
            campo.widget.attrs["class"] = "solo-lectura"


class LineaDeNotaCredito(LineaDeComprobante):
    """Una línea de la nota de crédito."""

    class Meta(LineaDeComprobante.Meta):
        model = NotaCreditoDetalle
        fields = ["producto", *LineaDeComprobante.Meta.fields]
        widgets = {**LineaDeComprobante.Meta.widgets, "producto": forms.HiddenInput()}


class LineaDeLiquidacionCompra(LineaDeComprobante):
    """Una línea de la liquidación de compra."""

    class Meta(LineaDeComprobante.Meta):
        model = LiquidacionCompraDetalle
        fields = ["producto", *LineaDeComprobante.Meta.fields]
        widgets = {**LineaDeComprobante.Meta.widgets, "producto": forms.HiddenInput()}


class MotivoDeNotaDebito(forms.ModelForm):
    """Una razón del cobro, con su valor."""

    razon = forms.CharField(label="Motivo", max_length=300)
    valor = CampoImporte(min_value=Decimal("0"), label="Valor")

    class Meta:
        model = NotaDebitoMotivo
        fields = ["razon", "valor"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["razon"].widget.attrs.update(caja(placeholder="Intereses por mora…"))
        _numero(self.fields["valor"])
        _columnas(self)


class BienTransportado(forms.ModelForm):
    """Un bien de los que van en la guía."""

    cantidad = CampoImporte(min_value=Decimal("0.000001"), initial=Decimal("1"), label="Cantidad")

    class Meta:
        model = GuiaDetalle
        fields = ["codigo_principal", "descripcion", "cantidad", "datos_adicionales"]
        labels = {"codigo_principal": "Código", "descripcion": "Qué se lleva"}
        widgets = {"datos_adicionales": forms.HiddenInput()}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["codigo_principal"].widget.attrs.update(caja(clase="campo-codigo"))
        self.fields["descripcion"].widget.attrs.update(caja(placeholder="Caja de 12…"))
        _numero(self.fields["cantidad"])
        _columnas(self)


class ImpuestoDeSustento(forms.ModelForm):
    """El IVA que trae el documento del proveedor (``impuestosDocSustento``)."""

    class Meta:
        model = RetencionDocSustentoImpuesto
        fields = ["codigo", "codigo_porcentaje", "base_imponible", "valor"]
        labels = {
            "codigo": "Impuesto",
            "codigo_porcentaje": "IVA del documento",
            "base_imponible": "Base imponible",
            "valor": "Valor del IVA",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for nombre in ("codigo", "codigo_porcentaje"):
            self.fields[nombre].widget.attrs.update(desplegable())
        for nombre in ("base_imponible", "valor"):
            _numero(self.fields[nombre])
        _columnas(self)


class RetencionDeSustento(forms.ModelForm):
    """Lo que se le retiene al proveedor: renta, IVA o ISD.

    El código no se escribe a mano: se elige de la tabla del SRI que está en la
    base, y con él llegan el concepto, el impuesto y el porcentaje.
    """

    class Meta:
        model = RetencionImpuesto
        fields = ["codigo", "codigo_retencion", "base_imponible", "porcentaje_retener", "valor_retenido"]
        labels = {
            "codigo": "Impuesto",
            "codigo_retencion": "Código de retención",
            "base_imponible": "Base imponible",
            "porcentaje_retener": "% a retener",
            "valor_retenido": "Valor retenido",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["codigo"].widget.attrs.update(desplegable())
        self.fields["codigo_retencion"].widget = SelectDeRetencion(
            choices=opciones_de_retencion(),
            datos=porcentajes_de_retencion(),
            attrs={
                **desplegable(),
                # La lista tiene más de cien conceptos: se eligen en su ventana, con
                # su buscador, y no se despliegan dentro del comprobante.
                "data-url": reverse("comprobantes:buscar_retenciones"),
            },
        )
        self.fields["codigo_retencion"].help_text = ""
        for nombre in ("base_imponible", "porcentaje_retener", "valor_retenido"):
            _numero(self.fields[nombre])
        _columnas(self)


# ------------------------------------------------------------- los formsets

#: El formset de líneas se pinta como una tabla y se guarda con la cabecera. Las filas
#: se añaden de una en una (con el buscador de productos o a mano), así que no se pide
#: ninguna de más.
_LINEAS = dict(extra=0, can_delete=True, can_order=False)

LineasDeNotaCredito = inlineformset_factory(
    NotaCredito, NotaCreditoDetalle, form=LineaDeNotaCredito, **_LINEAS
)
LineasDeLiquidacionCompra = inlineformset_factory(
    LiquidacionCompra, LiquidacionCompraDetalle, form=LineaDeLiquidacionCompra, **_LINEAS
)
MotivosDeNotaDebito = inlineformset_factory(
    NotaDebito, NotaDebitoMotivo, form=MotivoDeNotaDebito, **_LINEAS
)
BienesDeGuia = inlineformset_factory(
    GuiaDestinatario, GuiaDetalle, form=BienTransportado, **_LINEAS
)
ImpuestosDeRetencion = inlineformset_factory(
    RetencionDocSustento, RetencionDocSustentoImpuesto, form=ImpuestoDeSustento, **_LINEAS
)
RetencionesDeSustento = inlineformset_factory(
    RetencionDocSustento, RetencionImpuesto, form=RetencionDeSustento, **_LINEAS
)
