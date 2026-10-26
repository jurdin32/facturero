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
        initial=Decimal("0.00"),
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
        contado = self.desglose()
        del_desglose = total_del_desglose(contado)
        manual = datos.get("saldo_declarado")
        if contado:
            # Lo que se contó manda, aunque no haya nada: una caja puede cerrarse
            # vacía —todo se cobró con tarjeta o transferencia— y eso es un cierre
            # de 0,00, no un error.
            datos["saldo_declarado"] = del_desglose
        elif manual in (None, ""):
            datos["saldo_declarado"] = Decimal("0.00")
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


class ValeCajaForm(forms.Form):
    """El vale: a quién se le cobra (o a cuenta de quién va), cuánto y por qué."""

    responsable = forms.ModelChoiceField(
        queryset=None,
        label="Responsable",
        empty_label="Elija el responsable",
        help_text="A quién se le cobra el faltante o a cuenta de quién va el vale.",
    )
    tipo = forms.ChoiceField(
        label="Tipo",
        choices=(),
        initial="faltante",
        widget=forms.Select(attrs={"data-role": "select"}),
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
    motivo = forms.CharField(
        label="Motivo",
        max_length=200,
        widget=forms.TextInput(
            attrs=caja(icono="pencil", placeholder="Faltante del turno, anticipo de sueldo…")
        ),
    )
    nota = forms.CharField(
        label="Nota",
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "data-role": "textarea", "placeholder": "Lo que haya que dejar dicho."}
        ),
    )

    def __init__(self, *args: Any, sesion: Any = None, **kwargs: Any) -> None:
        from django.contrib.auth import get_user_model

        from .models import ValeCaja

        super().__init__(*args, **kwargs)
        self.sesion = sesion
        self.fields["responsable"].queryset = get_user_model().objects.filter(
            is_active=True
        ).order_by("first_name", "username")
        self.fields["tipo"].choices = ValeCaja.Tipo.choices
        if sesion is not None:
            self.fields["tipo"].initial = "faltante"
            falta = -sesion.diferencia if sesion.diferencia < 0 else Decimal("0")
            self.fields["importe"].initial = falta.quantize(Decimal("0.01"))
            self.fields["responsable"].initial = sesion.usuario_id
            self.fields["motivo"].initial = f"Faltante del turno del {sesion.cerrada_en:%d/%m/%Y}"
