"""Los formularios de la tienda: los datos de quien compra y las categorías.

El comprador no tiene cuenta: deja su nombre y, si quiere factura a su nombre, su
cédula o su RUC. El resto —el correo, el teléfono, la dirección de entrega y la
nota— es para poder entregarle el pedido. Las categorías se crean y se corrigen en
la aplicación, sin pasar por el admin.
"""

from __future__ import annotations

import re

from django import forms

from facturero.controles import caja, desplegable

from .models import Categoria, Pedido, Pregunta, Resena

__all__ = [
    "FormularioCategoria",
    "FormularioPedido",
    "FormularioPregunta",
    "FormularioResena",
]


class FormularioPedido(forms.ModelForm):
    """Los datos del pedido, con la identificación tal como la escribe la gente."""

    class Meta:
        model = Pedido
        fields = ["nombre", "identificacion", "email", "telefono", "direccion", "nota"]
        labels = {
            "nombre": "Nombre y apellido",
            "identificacion": "Cédula o RUC",
            "email": "Correo",
            "telefono": "Teléfono",
            "direccion": "Dirección de entrega",
            "nota": "Nota para el pedido",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs=caja(placeholder="Como consta en la cédula", autofocus=True)
            ),
            "identificacion": forms.TextInput(
                attrs=caja(
                    icono="user", placeholder="Opcional: sin ella se factura a consumidor final"
                )
            ),
            "email": forms.EmailInput(attrs=caja(icono="envelope", placeholder="Para avisarle")),
            "telefono": forms.TextInput(attrs=caja(icono="phone", placeholder="Para la entrega")),
            "direccion": forms.TextInput(
                attrs=caja(icono="location", placeholder="Dónde se entrega")
            ),
            "nota": forms.Textarea(
                attrs={"rows": 3, "data-role": "textarea", "placeholder": "Opcional"}
            ),
        }

    def clean_identificacion(self) -> str:
        """Solo números, y con la longitud de una cédula o de un RUC.

        Sin identificación se factura a consumidor final, que es lo que el SRI
        permite a quien no quiere dar sus datos.
        """
        identificacion = re.sub(r"\D", "", self.cleaned_data.get("identificacion") or "")
        if identificacion and len(identificacion) not in (10, 13):
            raise forms.ValidationError("La cédula tiene 10 dígitos y el RUC, 13.")
        return identificacion


class FormularioCategoria(forms.ModelForm):
    """Una categoría del catálogo, con su sitio en el árbol."""

    class Meta:
        model = Categoria
        fields = ["nombre", "padre", "descripcion", "orden", "activa", "slug"]
        labels = {
            "nombre": "Nombre",
            "padre": "Categoría de arriba",
            "descripcion": "Descripción",
            "orden": "Orden",
            "activa": "Activa",
            "slug": "Dirección",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs=caja(icono="folder", placeholder="Ropa, repuestos, accesorios…", autofocus=True)
            ),
            "padre": forms.Select(attrs=desplegable(icono="folder")),
            "descripcion": forms.TextInput(
                attrs=caja(placeholder="Opcional: lo que se lee en la cabecera")
            ),
            "slug": forms.TextInput(
                attrs=caja(icono="link", placeholder="Si se deja vacío, se arma con el nombre")
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        padres = Categoria.objects.all()
        if self.instance.pk:
            # Una categoría no puede colgar de sí misma; de sus hijas, lo dice clean().
            padres = padres.exclude(pk=self.instance.pk)
        self.fields["padre"].queryset = padres
        self.fields["padre"].label_from_instance = lambda categoria: categoria.ruta
        self.fields["orden"].required = False

    def clean_orden(self) -> int:
        return self.cleaned_data.get("orden") or 0


class FormularioPregunta(forms.ModelForm):
    """Lo que se pregunta desde la ficha, sin cuenta."""

    #: Un campo que nadie ve: si llega lleno, es un robot.
    trampa = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Pregunta
        fields = ["nombre", "email", "texto"]
        labels = {
            "nombre": "Su nombre",
            "email": "Correo (opcional)",
            "texto": "Su pregunta",
        }
        widgets = {
            "nombre": forms.TextInput(attrs=caja(placeholder="Cómo se llama")),
            "email": forms.EmailInput(attrs=caja(placeholder="Para avisarle la respuesta")),
            "texto": forms.Textarea(
                attrs={"rows": 3, "placeholder": "¿Qué quiere saber del producto?"}
            ),
        }

    def clean(self) -> dict:
        datos = super().clean()
        if (datos.get("trampa") or "").strip():
            raise forms.ValidationError("No se pudo enviar la pregunta.")
        return datos


class FormularioResena(forms.ModelForm):
    """La opinión de quien compró, con sus estrellas."""

    PALABRAS = {5: "Excelente", 4: "Muy bueno", 3: "Bueno", 2: "Regular", 1: "Malo"}

    ESTRELLAS = tuple(
        (nota, f"{'★' * nota}{'☆' * (5 - nota)}  {palabra}")
        for nota, palabra in PALABRAS.items()
    )

    calificacion = forms.TypedChoiceField(
        choices=ESTRELLAS, coerce=int, initial=5, label="Calificación"
    )
    trampa = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Resena
        fields = ["nombre", "email", "calificacion", "comentario"]
        labels = {
            "nombre": "Su nombre",
            "email": "Correo (opcional)",
            "comentario": "Su opinión",
        }
        widgets = {
            "nombre": forms.TextInput(attrs=caja(placeholder="Cómo se llama")),
            "email": forms.EmailInput(attrs=caja(placeholder="No se publica")),
            "comentario": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Qué le pareció el producto"}
            ),
        }

    def clean(self) -> dict:
        datos = super().clean()
        if (datos.get("trampa") or "").strip():
            raise forms.ValidationError("No se pudo enviar la reseña.")
        return datos
