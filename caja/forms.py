"""Formularios de la caja: abrir, mover y cerrar."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from facturero.controles import CampoImporte, caja

from .models import MovimientoCaja
from .servicios import DENOMINACIONES, total_del_desglose


class AbrirCajaForm(forms.Form):
    saldo_inicial = CampoImporte(
        label="Efectivo inicial",
        min_value=Decimal("0"),
        required=False,
        initial=Decimal("0.00"),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "data-role": "textarea",
                "data-prepend": "<span class='mif-pencil'></span>",
                "placeholder": "Novedades del turno, cambio de caja…",
            }
        ),
    )


class MovimientoCajaForm(forms.Form):
    tipo = forms.ChoiceField(
        label="Tipo",
        choices=MovimientoCaja.Tipo.choices,
        widget=forms.Select(
            attrs={
                "data-role": "select",
                "data-prepend": "<span class='mif-data-exchange'></span>",
            }
        ),
    )
    concepto = forms.CharField(
        label="Concepto",
        max_length=200,
        widget=forms.TextInput(
            attrs=caja(icono="pencil", placeholder="Qué entró o qué salió")
        ),
    )
    referencia = forms.CharField(
        label="Referencia",
        max_length=120,
        required=False,
        widget=forms.TextInput(
            attrs=caja(icono="tag", placeholder="Factura, recibo, vale…")
        ),
    )
    importe = CampoImporte(
        label="Importe",
        min_value=Decimal("0.01"),
        widget=forms.TextInput(
            attrs={
                "class": "campo-num",
                "inputmode": "decimal",
                "autocomplete": "off",
                "data-role": "input",
                "data-prepend": "<span class='mif-dollar'></span>",
            }
        ),
    )


class CerrarCajaForm(forms.Form):
    """El cierre: el desglose de lo contado manda, con el total a la vista.

    Se cuenta billete por billete y moneda por moneda —como se hace el arqueo sobre
    la mesa— y el total sale de la suma. También se puede escribir el efectivo
    contado a mano, para cuando el conteo se hizo aparte: en ese caso se toma ese
    valor y el desglose queda como detalle.
    """

    saldo_declarado = CampoImporte(
        label="Efectivo contado",
        min_value=Decimal("0"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "campo-num",
                "inputmode": "decimal",
                "autocomplete": "off",
                "data-role": "input",
                "data-prepend": "<span class='mif-coins'></span>",
            }
        ),
    )
    observaciones_cierre = forms.CharField(
        label="Observaciones del cierre",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "data-role": "textarea",
                "data-prepend": "<span class='mif-pencil'></span>",
                "placeholder": "Si falta o sobra efectivo, explique por qué.",
            }
        ),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Una casilla por denominación, con el valor en la etiqueta.
        for valor in DENOMINACIONES:
            self.fields[self._campo(valor)] = forms.IntegerField(
                label=f"{valor:.2f}",
                required=False,
                min_value=0,
                initial=0,
                widget=forms.NumberInput(
                    attrs={
                        "class": "campo-num desglose-cantidad",
                        "inputmode": "numeric",
                        "autocomplete": "off",
                        "min": 0,
                        "step": 1,
                        "data-valor": f"{valor:.2f}",
                        "aria-label": f"Cuántos de {valor:.2f} dólares",
                    }
                ),
            )

    @staticmethod
    def _campo(valor: Decimal) -> str:
        """El nombre del campo de una denominación: ``cantidad_100_00``."""
        return "cantidad_" + f"{valor:.2f}".replace(".", "_")

    def desglose(self) -> dict[str, int]:
        """Las cantidades contadas, por valor, sin las que están en cero."""
        datos = {}
        for valor in DENOMINACIONES:
            cantidad = self.cleaned_data.get(self._campo(valor)) or 0
            if cantidad:
                datos[f"{valor:.2f}"] = int(cantidad)
        return datos

    def clean(self):
        datos = super().clean()
        del_desglose = total_del_desglose(self.desglose())
        if del_desglose:
            # Lo que se contó manda: el total escrito a mano solo se usa si no se
            # contó nada por denominación.
            datos["saldo_declarado"] = del_desglose
        elif datos.get("saldo_declarado") in (None, ""):
            raise forms.ValidationError(
                "Cuente los billetes y las monedas, o escriba el efectivo contado."
            )
        return datos

    def renglones(self) -> list[dict]:
        """Los billetes y las monedas, con lo que suman, para pintar la tabla."""
        renglones = []
        for valor in DENOMINACIONES:
            campo = self[self._campo(valor)]
            cantidad = campo.value() or 0
            try:
                cantidad = int(cantidad)
            except (TypeError, ValueError):
                cantidad = 0
            renglones.append(
                {
                    "valor": valor,
                    "campo": campo,
                    "cantidad": cantidad,
                    "subtotal": valor * cantidad,
                    "es_billete": valor >= 1,
                }
            )
        return renglones
