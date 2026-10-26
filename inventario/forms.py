"""Formulario de movimientos de inventario."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django import forms
from factec.django.documentos import Producto
from factec.sri.fechas import hoy_en_ecuador

from facturero.controles import caja, desplegable, fecha, numero
from facturacion.forms import CampoImporte

from .models import Movimiento, TipoMovimiento

__all__ = ["FormularioMovimiento"]

#: Los tipos que se pueden registrar a mano (el de factura lo pone la facturación).
TIPOS_A_MANO = (
    (TipoMovimiento.ENTRADA.value, "Entrada (compra o devolución)"),
    (TipoMovimiento.SALIDA.value, "Salida (venta sin factura, consumo, merma)"),
    (TipoMovimiento.AJUSTE.value, "Ajuste (lo que hay contado: use + o −)"),
)


class FormularioMovimiento(forms.ModelForm):
    """Mueve el stock y deja la constancia en el libro."""

    cantidad = CampoImporte(label="Cantidad")

    class Meta:
        model = Movimiento
        fields = ["fecha", "tipo", "cantidad", "costo_unitario", "motivo", "referencia"]
        labels = {
            "fecha": "Fecha",
            "tipo": "Qué pasó",
            "cantidad": "Cantidad",
            "costo_unitario": "Costo unitario",
            "motivo": "Motivo",
            "referencia": "Referencia",
        }
        widgets = {
            "fecha": forms.DateInput(format="%Y-%m-%d", attrs=fecha()),
            "tipo": forms.Select(choices=TIPOS_A_MANO, attrs=desplegable(icono="history")),
            "costo_unitario": forms.TextInput(attrs=numero(icono="dollar")),
            "motivo": forms.TextInput(
                attrs=caja(icono="pencil", placeholder="compra a…, merma, conteo físico…")
            ),
            "referencia": forms.TextInput(
                attrs=caja(icono="tag", placeholder="nº de compra, de guía…")
            ),
        }

    def __init__(self, *args: Any, producto: Optional[Producto] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if producto is not None:
            self.instance.producto = producto
        self.fields["fecha"].initial = self.fields["fecha"].initial or hoy_en_ecuador()
        self.fields["fecha"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["cantidad"].widget.attrs.update(numero(icono="shuffle"))
        self.fields["costo_unitario"].widget.attrs.update(numero(icono="dollar"))
        self.fields["cantidad"].localize = False
        # El hueco del desplegable se dice en castellano, no con el guion de Django.
        self.fields["tipo"].choices = [("", "— qué pasó —"), *TIPOS_A_MANO]
        self.fields["tipo"].widget.attrs.update(desplegable(icono="history"))

    def clean(self) -> dict:
        datos = super().clean()
        tipo = datos.get("tipo")
        cantidad = datos.get("cantidad")
        if cantidad is None:
            return datos
        if tipo == TipoMovimiento.AJUSTE.value:
            if cantidad == Decimal("0"):
                raise forms.ValidationError("Un ajuste de cero no cambia nada.")
        elif cantidad <= 0:
            raise forms.ValidationError(
                {"cantidad": "Escriba una cantidad mayor que cero (el tipo ya dice si entra o sale)."}
            )
        return datos
