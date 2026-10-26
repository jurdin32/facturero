"""Formularios de la interfaz: la factura y sus líneas.

Son formularios de los modelos del paquete (``factec.django.documentos``), con los
campos que de verdad se llenan al facturar y los widgets con el estilo de la casa.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.forms import inlineformset_factory

from factec.django.documentos import Factura, FacturaDetalle
from factec.django.forms import LineaDocumentoForm

from facturero.controles import CampoImporte, caja, desplegable, fecha

__all__ = ["CampoImporte", "FormularioFactura", "FormularioDetalle", "DetallesDeFactura"]


def _numero(campo: forms.Field) -> forms.Field:
    """Deja un campo de números listo para el CSS propio.

    El navegador no acepta «1.234,56» en un ``type=number``: van como texto con el
    teclado decimal, que es lo que se escribe aquí.
    """
    campo.localize = False
    if hasattr(campo.widget, "input_type"):
        campo.widget.input_type = "text"
    campo.widget.attrs.update(
        {"class": "campo-num", "inputmode": "decimal", "autocomplete": "off"}
    )
    return campo


class FormularioFactura(forms.ModelForm):
    """Los datos de la factura. Las líneas van aparte."""

    plazo = CampoImporte(required=False, decimal_places=2, label="Plazo")

    class Meta:
        model = Factura
        fields = [
            "receptor", "fecha_emision", "forma_pago", "plazo", "unidad_tiempo",
            "observaciones", "informacion_adicional",
        ]
        labels = {
            "receptor": "Cliente",
            "fecha_emision": "Fecha de emisión",
            "forma_pago": "Forma de pago",
            "plazo": "Plazo",
            "unidad_tiempo": "Unidad",
            "observaciones": "Observaciones",
            "informacion_adicional": "Información adicional",
        }
        help_texts = {
            "fecha_emision": "Al emitir se ajusta sola al día de la firma.",
            "observaciones": "Las lee el cliente en el comprobante.",
            "informacion_adicional": "NOMBRE=VALOR separados por «;», hasta 15 campos.",
        }
        widgets = {
            "fecha_emision": forms.DateInput(format="%Y-%m-%d", attrs=fecha()),
            "receptor": forms.Select(attrs=desplegable(icono="person", clase="campo-cliente")),
            "forma_pago": forms.Select(attrs=desplegable(icono="credit-card")),
            "unidad_tiempo": forms.TextInput(
                attrs=caja(
                    icono="history", placeholder="días, meses o años", list="unidades-de-tiempo"
                )
            ),
            "observaciones": forms.Textarea(
                attrs={"rows": 2, "data-role": "textarea", "data-prepend": "<span class='mif-pencil'></span>"}
            ),
            "informacion_adicional": forms.Textarea(
                attrs={"rows": 2, "data-role": "textarea", "data-prepend": "<span class='mif-tag'></span>"}
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["fecha_emision"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["receptor"].queryset = self.fields["receptor"].queryset.order_by("razon_social")
        self.fields["receptor"].empty_label = "— Elija el cliente —"
        _numero(self.fields["plazo"])


class FormularioDetalle(LineaDocumentoForm):
    """Una línea de la factura: qué se factura y a cuánto.

    Hereda del formulario de línea del paquete: lo que falte lo completa él desde
    el producto elegido (descripción, códigos, unidad, precio e IVA) y solo lo pide
    cuando la línea va suelta. Aquí se cambia el aspecto y que las cantidades se
    escriban como se dicen aquí: 1.234,56.
    """

    # Al facturar casi todo es una unidad: la hoja viene con 1 puesto y se cambia
    # solo cuando son varias.
    cantidad = CampoImporte(min_value=Decimal("0.000001"), initial=Decimal("1"), label="Cantidad")
    precio_unitario = CampoImporte(min_value=Decimal("0"), required=False, label="Precio")
    descuento = CampoImporte(min_value=Decimal("0"), required=False, label="Descuento")

    class Meta(LineaDocumentoForm.Meta):
        model = FacturaDetalle
        # La unidad de medida y el código auxiliar los trae el producto; van en la
        # línea porque el XML los lleva y el SRI los pide.
        fields = [
            "producto", "codigo_principal", "descripcion", "unidad_medida", "cantidad",
            "precio_unitario", "descuento", "codigo_porcentaje_iva", "codigo_auxiliar",
            "datos_adicionales",
        ]
        labels = {
            "producto": "Del catálogo",
            "codigo_principal": "Código",
            "descripcion": "Descripción",
            "codigo_porcentaje_iva": "IVA",
            "datos_adicionales": "Adicionales",
        }
        # En la hoja se ve la descripción, la cantidad, el precio y el descuento. Lo
        # demás (el producto, su código, la unidad y la tarifa de IVA) lo trae el
        # catálogo y viaja en la línea, pero no se pregunta: es lo que el documento
        # lleva escrito igual.
        widgets = {
            "producto": forms.HiddenInput(),
            "codigo_principal": forms.HiddenInput(),
            "unidad_medida": forms.HiddenInput(),
            "codigo_porcentaje_iva": forms.HiddenInput(),
            "descuento": forms.TextInput(
                attrs={
                    "placeholder": "0,00",
                    "autocomplete": "off",
                    "inputmode": "decimal",
                    "class": "campo-descuento",
                }
            ),
            "descripcion": forms.TextInput(
                attrs={
                    "placeholder": "Qué se factura",
                    "autocomplete": "off",
                    "class": "campo-descripcion",
                }
            ),
            "codigo_auxiliar": forms.HiddenInput(),
            "datos_adicionales": forms.HiddenInput(),
        }

    @property
    def errores_con_nombre(self) -> list[tuple[str, str]]:
        """Los errores con el nombre del campo: «obligatorio» a secas no dice nada."""
        avisos = []
        for nombre, lista in self.errors.items():
            etiqueta = "Línea" if nombre == "__all__" else (self.fields[nombre].label or nombre)
            avisos.extend((etiqueta, mensaje) for mensaje in lista)
        return avisos

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = (
            self.fields["producto"].queryset.filter(activo=True).order_by("descripcion")
        )
        self.fields["producto"].empty_label = "— del catálogo —"
        self.fields["producto"].required = False
        for nombre in ("cantidad", "precio_unitario", "descuento"):
            _numero(self.fields[nombre])
        # Las filas que se dejan en blanco tienen que contar como «sin tocar»: el
        # modelo trae valores por omisión (precio 0, IVA 4) y, con el precio y el IVA
        # vacíos en el navegador, la fila parecía cambiada y pedía lo que nadie
        # escribió. Solo vale para las líneas nuevas: una guardada enseña lo suyo.
        if not self.instance.pk:
            for nombre in self.EN_BLANCO_AL_CREAR:
                if nombre in self.fields:
                    self.initial[nombre] = ""


DetallesDeFactura = inlineformset_factory(
    Factura,
    FacturaDetalle,
    form=FormularioDetalle,
    # La tabla se construye con lo que se elige en el buscador, así que no se
    # pintan líneas vacías de antemano. Que la factura no salga sin ninguna línea
    # se comprueba al guardar, con un aviso que se entiende.
    extra=0,
    can_delete=True,
)
