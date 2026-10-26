"""Formularios del catálogo: productos, servicios y clientes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.urls import reverse_lazy
from factec.django.documentos import (
    OPCIONES_TARIFA_IVA,
    OPCIONES_TIPO_IDENTIFICACION,
    UNIDAD_POR_TIPO,
    Cliente,
    Conductor,
    Producto,
    TipoProducto,
    Vehiculo,
)

from facturero.controles import caja, desplegable, numero
from facturacion.forms import CampoImporte

__all__ = [
    "FormularioProducto",
    "FormularioCliente",
    "FormularioConductor",
    "FormularioVehiculo",
]


class FormularioProducto(forms.ModelForm):
    """Un bien o un servicio del catálogo.

    Si es un bien, se le puede decir con cuánto empieza: eso queda como el primer
    movimiento del inventario, para que el kardex tenga sentido desde el principio.
    """

    stock_inicial = CampoImporte(
        required=False, min_value=Decimal("0"), label="Con cuánto empieza",
        help_text="Solo al crearlo: queda como el primer movimiento del inventario.",
    )
    minimo = CampoImporte(
        required=False, min_value=Decimal("0"), label="Mínimo para reponer",
        help_text="Con 0 no se avisa de nada.",
    )
    ubicacion = forms.CharField(
        required=False, max_length=60, label="Ubicación",
        widget=forms.TextInput(
            attrs=caja(icono="location", placeholder="bodega, estante…")
        ),
    )

    class Meta:
        model = Producto
        fields = [
            "tipo", "codigo_principal", "descripcion", "unidad_medida", "precio_unitario",
            "codigo_porcentaje_iva", "codigo_auxiliar", "datos_adicionales", "activo",
        ]
        labels = {
            "tipo": "¿Qué es?",
            "codigo_principal": "Código",
            "descripcion": "Descripción",
            "unidad_medida": "Unidad",
            "precio_unitario": "Precio",
            "codigo_porcentaje_iva": "IVA",
            "codigo_auxiliar": "Código auxiliar",
            "datos_adicionales": "Detalles adicionales",
            "activo": "Se puede facturar",
        }
        widgets = {
            "tipo": forms.Select(attrs=desplegable(icono="cube")),
            "codigo_principal": forms.TextInput(
                attrs=caja(icono="tag", placeholder="DSW, PROD-01…", autofocus=True)
            ),
            "descripcion": forms.TextInput(
                attrs=caja(placeholder="Qué es, como sale en la factura")
            ),
            "unidad_medida": forms.TextInput(
                attrs=caja(placeholder="unidad, caja, kg, hora…")
            ),
            "codigo_porcentaje_iva": forms.Select(
                choices=OPCIONES_TARIFA_IVA, attrs=desplegable(icono="percent")
            ),
            "codigo_auxiliar": forms.TextInput(attrs=caja(icono="barcode")),
            "activo": forms.CheckboxInput(),
            "datos_adicionales": forms.TextInput(
                attrs=caja(placeholder="MARCA=ACME; GARANTIA=12 MESES")
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["precio_unitario"] = CampoImporte(
            min_value=Decimal("0"), decimal_places=6, label="Precio"
        )
        for nombre in ("precio_unitario", "stock_inicial", "minimo"):
            self.fields[nombre].widget.attrs.update(numero())
        if self.instance.pk:
            # El stock no se cambia aquí: se mueve con entradas, salidas y ajustes.
            self.fields.pop("stock_inicial")
            existencia = getattr(self.instance, "existencia", None)
            self.fields["minimo"].initial = existencia.minimo if existencia else None
            self.fields["ubicacion"].initial = existencia.ubicacion if existencia else ""

    def clean(self) -> dict:
        datos = super().clean()
        if not datos.get("unidad_medida"):
            tipo = datos.get("tipo") or TipoProducto.PRODUCTO.value
            datos["unidad_medida"] = UNIDAD_POR_TIPO.get(tipo, "UNIDAD")
        return datos

    @property
    def es_bien(self) -> bool:
        return (self.instance.tipo or TipoProducto.PRODUCTO.value) == TipoProducto.PRODUCTO.value


class FormularioCliente(forms.ModelForm):
    """Quién compra: los datos que van en la factura."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Solo al darlo de alta: al corregir un cliente ya guardado no hay que
        # salir al SRI ni pisar lo que está escrito.
        if not self.instance.pk:
            self.fields["identificacion"].widget.attrs["data-consultar-ruc"] = str(
                reverse_lazy("catalogos:consultar_identificacion")
            )

    class Meta:
        model = Cliente
        fields = [
            "razon_social", "tipo_identificacion", "identificacion", "direccion",
            "email", "telefono",
        ]
        labels = {
            "razon_social": "Razón social",
            "tipo_identificacion": "Tipo",
            "identificacion": "RUC o cédula",
            "direccion": "Dirección",
            "email": "Correo",
            "telefono": "Teléfono",
        }
        widgets = {
            "razon_social": forms.TextInput(
                attrs=caja(icono="shop", placeholder="Como sale en la factura", autofocus=True)
            ),
            "tipo_identificacion": forms.Select(
                choices=OPCIONES_TIPO_IDENTIFICACION, attrs=desplegable(icono="person-card")
            ),
            "identificacion": forms.TextInput(
                attrs=caja(clase="mono", inputmode="numeric")
            ),
            "direccion": forms.TextInput(attrs=caja(icono="location")),
            "email": forms.EmailInput(attrs=caja(icono="email")),
            "telefono": forms.TextInput(attrs=caja(icono="phone")),
        }


class FormularioConductor(forms.ModelForm):
    """Quién transporta: los datos que el SRI pide como transportista.

    Es la otra mitad de la guía de remisión, junto con el vehículo: se da de alta
    una vez y después se elige en cada guía.
    """

    class Meta:
        model = Conductor
        fields = ["razon_social", "tipo_identificacion", "identificacion", "telefono", "activo"]
        labels = {
            "razon_social": "Nombre o razón social",
            "tipo_identificacion": "Tipo",
            "identificacion": "RUC o cédula",
            "telefono": "Teléfono",
            "activo": "Se ofrece al hacer la guía",
        }
        widgets = {
            "razon_social": forms.TextInput(
                attrs=caja(icono="shop", placeholder="Como consta en el RUC", autofocus=True)
            ),
            "tipo_identificacion": forms.Select(
                choices=OPCIONES_TIPO_IDENTIFICACION, attrs=desplegable(icono="person-card")
            ),
            "identificacion": forms.TextInput(attrs=caja(icono="person-card", clase="mono")),
            "telefono": forms.TextInput(attrs=caja(icono="phone")),
            "activo": forms.CheckboxInput(),
        }


class FormularioVehiculo(forms.ModelForm):
    """El vehículo: de aquí sale la placa que pide la guía de remisión."""

    class Meta:
        model = Vehiculo
        fields = ["placa", "descripcion", "activo"]
        labels = {
            "placa": "Placa",
            "descripcion": "Descripción",
            "activo": "Se ofrece al hacer la guía",
        }
        widgets = {
            "placa": forms.TextInput(
                attrs=caja(icono="truck", clase="mono", placeholder="PBX-1234", autofocus=True)
            ),
            "descripcion": forms.TextInput(
                attrs=caja(placeholder="Marca, modelo o como lo llamen en el taller")
            ),
            "activo": forms.CheckboxInput(),
        }
