"""Los formularios de la seguridad: el rol, sus permisos y quién los lleva.

Los permisos se marcan con **casillas**: cada opción de la aplicación trae una
casilla de «leer» y otra de «escribir», en vez de un desplegable. En una lista de
dieciséis opciones lo que se hace es marcar, y así se ve de un vistazo qué queda
marcado. Escribir ya incluye leer: quien puede modificar, puede mirar.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from personalize_options import opciones as registro
from personalize_options.models import Nivel, Opcion, Permiso, Rol

from facturero.controles import caja

__all__ = [
    "FormularioOpcion",
    "FormularioDatosDelRol",
    "FormularioPermisos",
    "FormularioRoles",
    "FormularioUsuario",
    "casillas_del_formulario",
]

#: Lo que se le pone delante al nombre de cada casilla.
LEER = "leer_"
ESCRIBIR = "escribir_"


class FormularioOpcion(forms.ModelForm):
    """Una opción: la pantalla o el apartado que se puede permitir o negar.

    Se crea desde aquí y con eso ya sale en el asistente de los roles; si además se
    le pone dirección, sale en el menú.
    """

    class Meta:
        model = Opcion
        fields = ["nombre", "clave", "categoria", "grupo", "url", "icono", "en_menu", "activo"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["nombre"].widget.attrs.update(
            caja(icono="receipt", placeholder="Reportes de ventas")
        )
        self.fields["clave"].widget.attrs.update(
            caja(icono="tag", placeholder="reportes")
        )
        self.fields["categoria"].required = False
        self.fields["categoria"].help_text = (
            "Con qué categoría se agrupa en el asistente del rol. Si se escribe un "
            "apartado suelto, se usa ese."
        )
        self.fields["grupo"].required = False
        self.fields["grupo"].widget.attrs.update(
            caja(icono="folder", placeholder="Solo si no se elige categoría")
        )
        self.fields["grupo"].label = "Apartado suelto"
        self.fields["url"].widget.attrs.update(
            caja(icono="link", placeholder="/reportes/")
        )
        self.fields["icono"].widget.attrs.update(
            caja(icono="star-full", placeholder="pie-chart")
        )
        # Para que el navegador sugiera los apartados que ya hay, y no se escriban
        # dos parecidos («Catálogo» y «Catalogo»).
        self.fields["grupo"].widget.attrs["list"] = "apartados-conocidos"
        if not self.instance.pk:
            # La opción nueva entra al final; después se mueve arrastrando.
            ultimo = (
                Opcion.objects.order_by("-orden").values_list("orden", flat=True).first()
            )
            self.instance.orden = (ultimo or 0) + 1

    @property
    def apartados_conocidos(self) -> List[str]:
        """Los apartados que ya tienen alguna opción, para el desplegable."""
        return [grupo for grupo, _ in registro.grupos()]


class FormularioDatosDelRol(forms.ModelForm):
    """Lo del rol: cómo se llama, para qué es, si está activo y quién lo lleva."""

    class Meta:
        model = Rol
        fields = ["nombre", "descripcion", "activo", "usuarios"]
        labels = {
            "nombre": "Nombre",
            "descripcion": "Para qué es",
            "activo": "Activo",
            "usuarios": "Quién lo lleva",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs=caja(icono="security", placeholder="Facturador, Bodega, Contabilidad…")
            ),
            "descripcion": forms.TextInput(
                attrs=caja(icono="info", placeholder="Para qué es este rol")
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["usuarios"].help_text = (
            "Mantenga pulsado Ctrl (o Cmd) para elegir varios."
        )


class FormularioPermisos(forms.Form):
    """Lo que puede el rol, opción por opción, con dos casillas por opción."""

    def __init__(self, *args: Any, rol: Optional[Rol] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.rol = rol
        self.opciones = registro.todas(solo_activas=True)
        puestos = rol.opciones if rol is not None and rol.pk else {}
        for opcion in self.opciones:
            nivel = puestos.get(opcion.clave, "")
            self.fields[LEER + opcion.clave] = forms.BooleanField(
                required=False,
                label="Leer",
                initial=nivel in (Nivel.LECTURA.value, Nivel.ESCRITURA.value),
            )
            self.fields[ESCRIBIR + opcion.clave] = forms.BooleanField(
                required=False,
                label="Escribir",
                initial=nivel == Nivel.ESCRITURA.value,
            )

    def clean(self) -> Dict[str, Any]:
        """Escribir incluye leer: no se puede modificar lo que no se ve."""
        datos = super().clean()
        for opcion in self.opciones:
            if datos.get(ESCRIBIR + opcion.clave):
                datos[LEER + opcion.clave] = True
        return datos

    def nivel_de(self, clave: str) -> str:
        """El nivel que queda marcado para esa opción (nada, si no se marcó)."""
        if self.cleaned_data.get(ESCRIBIR + clave):
            return Nivel.ESCRITURA.value
        if self.cleaned_data.get(LEER + clave):
            return Nivel.LECTURA.value
        return ""

    @property
    def opciones_marcadas(self) -> int:
        """Cuántas opciones quedan con algo marcado (para el resumen)."""
        return sum(1 for opcion in self.opciones if self.nivel_de(opcion.clave))

    @property
    def con_escritura(self) -> int:
        """Cuántas quedan para modificar."""
        return sum(
            1
            for opcion in self.opciones
            if self.nivel_de(opcion.clave) == Nivel.ESCRITURA.value
        )

    def guardar_en(self, rol: Rol) -> int:
        """Deja en el rol lo marcado: lo que no esté marcado, se quita."""
        cuantas = 0
        for opcion in self.opciones:
            nivel = self.nivel_de(opcion.clave)
            if nivel:
                Permiso.objects.update_or_create(
                    rol=rol, opcion=opcion.clave, defaults={"nivel": nivel}
                )
                cuantas += 1
            else:
                Permiso.objects.filter(rol=rol, opcion=opcion.clave).delete()
        return cuantas


def casillas_del_formulario(
    formulario: FormularioPermisos,
) -> List[Tuple[str, List[Tuple[Opcion, Any, Any]]]]:
    """Las casillas de cada opción, agrupadas por apartado (para la plantilla).

    De cada opción salen las dos casillas, la de leer y la de escribir.
    """
    return [
        (
            grupo,
            [
                (
                    opcion,
                    formulario[f"{LEER}{opcion.clave}"],
                    formulario[f"{ESCRIBIR}{opcion.clave}"],
                )
                for opcion in opciones
            ],
        )
        for grupo, opciones in registro.grupos(solo_activas=True)
    ]


class FormularioRoles(forms.Form):
    """Los roles que lleva una persona.

    Se marca el rol entero, no sus opciones: las opciones se deciden una vez, en el
    rol, y así darle a alguien «Bodega» no es volver a marcar treinta casillas.
    """

    roles = forms.ModelMultipleChoiceField(
        queryset=Rol.objects.none(),
        required=False,
        label="Roles",
        help_text="Sin ningún rol no podrá nada, si la aplicación está en modo cerrado.",
    )

    def __init__(self, *args: Any, persona: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Los que están activos y, además, los que la persona ya lleva: un rol
        # apagado que alguien tenga se sigue viendo, para poder quitárselo.
        disponibles = Q(activo=True)
        if getattr(persona, "pk", None):
            disponibles |= Q(usuarios=persona)
        self.fields["roles"].queryset = (
            Rol.objects.filter(disponibles)
            .distinct()
            .annotate(
                cuantas_opciones=Count("permisos", distinct=True),
                con_escritura=Count(
                    "permisos", filter=Q(permisos__nivel=Nivel.ESCRITURA.value), distinct=True
                ),
            )
            .order_by("nombre")
        )


class FormularioUsuario(forms.ModelForm):
    """El alta y la corrección de una persona, sin pasar por el admin.

    Se piden los datos de la cuenta, la clave —que se escribe dos veces— y el rol o
    los roles que va a llevar. La clave no se guarda en claro: se pasa por el mismo
    `set_password` del admin, y de ahí en adelante solo queda su huella.

    Al corregir una cuenta la clave es opcional: si se deja en blanco, se queda la que
    tenía. Así se puede cambiar el nombre o el correo sin obligar a cambiarla.
    """

    clave = forms.CharField(
        label="Clave",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "data-role": "input",
                "data-prepend": "<span class='mif-key'></span>",
            }
        ),
        help_text="Al menos 8 caracteres y que no sea una clave común.",
    )
    clave2 = forms.CharField(
        label="Repetir la clave",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "data-role": "input",
                "data-prepend": "<span class='mif-key'></span>",
            }
        ),
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Rol.objects.none(),
        required=False,
        label="Roles",
        widget=forms.CheckboxSelectMultiple,
        help_text="Se marca el rol entero: lo que puede cada uno se decide en el rol.",
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "is_active"]
        labels = {
            "username": "Usuario",
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "email": "Correo",
            "is_active": "Puede entrar",
        }
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "autocomplete": "off",
                    "data-role": "input",
                    "data-prepend": "<span class='mif-person'></span>",
                }
            ),
            "first_name": forms.TextInput(attrs={"data-role": "input"}),
            "last_name": forms.TextInput(attrs={"data-role": "input"}),
            "email": forms.EmailInput(
                attrs={
                    "autocomplete": "off",
                    "data-role": "input",
                    "data-prepend": "<span class='mif-mail'></span>",
                }
            ),
        }

    def __init__(self, *args: Any, persona: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.persona = persona or self.instance
        es_nueva = not getattr(self.persona, "pk", None)
        if es_nueva:
            self.fields["is_active"].initial = True
            self.fields["clave"].required = True
            self.fields["clave"].help_text = (
                "Al menos 8 caracteres y que no sea una clave común."
            )
        else:
            self.fields["clave"].help_text = "Déjela en blanco para no cambiarla."
            self.fields["is_active"].help_text = (
                "Si se desmarca, la persona no puede entrar, pero no se borra nada."
            )

        disponibles = Q(activo=True)
        if getattr(self.persona, "pk", None):
            disponibles |= Q(usuarios=self.persona)
        self.fields["roles"].queryset = Rol.objects.filter(disponibles).distinct().order_by("nombre")
        if self.persona.pk:
            self.fields["roles"].initial = self.persona.roles.all()

    def clean_username(self) -> str:
        usuario = (self.cleaned_data["username"] or "").strip()
        repetido = get_user_model().objects.filter(username__iexact=usuario)
        if self.persona.pk:
            repetido = repetido.exclude(pk=self.persona.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya hay una cuenta con ese nombre de usuario.")
        return usuario

    def clean(self) -> Dict[str, Any]:
        datos = super().clean()
        clave = datos.get("clave") or ""
        repetida = datos.get("clave2") or ""
        if clave or repetida:
            if clave != repetida:
                self.add_error("clave2", "Las dos claves no son iguales.")
            else:
                try:
                    validate_password(clave, self.persona)
                except ValidationError as error:
                    for mensaje in error.messages:
                        self.add_error("clave", mensaje)
        return datos

    def save(self, commit: bool = True) -> Any:
        persona = super().save(commit=False)
        clave = self.cleaned_data.get("clave") or ""
        if clave:
            persona.set_password(clave)
        if commit:
            persona.save()
            persona.roles.set(self.cleaned_data.get("roles") or [])
        return persona
