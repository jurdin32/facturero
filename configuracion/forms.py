"""Los formularios del asistente de configuración del SRI.

El paquete factec trae un formulario que hace todo de una vez (el del admin). El
asistente lo parte en tres, uno por paso: los datos del contribuyente, lo del SRI
(ambiente y serie) y el certificado de firma. Cada formulario se apoya en lo que
el propio modelo ya valida —RUC, establecimiento, punto de emisión y campos
adicionales— y en las utilidades del paquete para consultar el catastro del SRI y
abrir el ``.p12``, que es la única forma de saber que la contraseña es la buena.
"""

from __future__ import annotations

from typing import Any, Dict, List

from django import forms
from factec.django import sri_datos
from factec.django.models import (
    EXTENSIONES_CERTIFICADO,
    ConfiguracionEmisor,
    TipoComprobante,
)
from factec.excepciones import ErrorFacturacion

from facturero.controles import caja, desplegable, numero

from .models import EXTENSIONES_LOGO, TAMANO_MAXIMO_LOGO, LogoEmisor

__all__ = [
    "FormularioEmisor",
    "FormularioSRI",
    "FormularioSecuencial",
    "FormularioSecuenciales",
    "FormularioCertificado",
    "FormularioLogo",
]


class FormularioEmisor(forms.ModelForm):
    """Paso 1: quién emite y qué obligaciones tiene declaradas.

    Si se marca «traer los datos del SRI», al guardar se consulta el catastro y se
    rellenan solos la razón social, el régimen, la categoría y la obligación de
    llevar contabilidad. Lo que ya venga escrito no se pisa.
    """

    consultar_sri = forms.BooleanField(
        label="Traer los datos del RUC del SRI",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(),
        help_text=(
            "Rellena la razón social, el régimen, la categoría y lo de llevar "
            "contabilidad con lo que publica el SRI. Necesita conexión."
        ),
    )

    class Meta:
        model = ConfiguracionEmisor
        fields = (
            "ruc",
            "razon_social",
            "nombre_comercial",
            "dir_matriz",
            "dir_establecimiento",
            "obligado_contabilidad",
            "contribuyente_especial",
            "agente_retencion",
            "regimen",
            "categoria",
            "campos_adicionales",
        )
        labels = {
            "ruc": "RUC",
            "razon_social": "Razón social",
            "nombre_comercial": "Nombre comercial",
            "dir_matriz": "Dirección de la matriz",
            "dir_establecimiento": "Dirección del establecimiento",
            "obligado_contabilidad": "Lleva contabilidad",
            "contribuyente_especial": "N.º de contribuyente especial",
            "agente_retencion": "N.º de agente de retención",
            "regimen": "Régimen",
            "categoria": "Categoría",
            "campos_adicionales": "Campos adicionales de la tienda",
        }
        widgets = {
            "ruc": forms.TextInput(attrs=caja(icono="person-card", autofocus=True)),
            "razon_social": forms.TextInput(attrs=caja(icono="shop")),
            "nombre_comercial": forms.TextInput(
                attrs=caja(icono="shop", placeholder="Como lo conoce el cliente")
            ),
            "dir_matriz": forms.TextInput(
                attrs=caja(icono="location", placeholder="calle y número, ciudad")
            ),
            "dir_establecimiento": forms.TextInput(
                attrs=caja(icono="location", placeholder="si es otra que la matriz")
            ),
            "obligado_contabilidad": forms.CheckboxInput(),
            "contribuyente_especial": forms.TextInput(attrs=caja(icono="award")),
            "agente_retencion": forms.TextInput(attrs=caja(icono="award")),
            "regimen": forms.TextInput(attrs=caja(placeholder="RIMPE, general…")),
            "categoria": forms.TextInput(attrs=caja(placeholder="Negocio popular…")),
            "campos_adicionales": forms.TextInput(
                attrs=caja(placeholder="VENDEDOR=JOHNNY; SUCURSAL=NORTE")
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        #: Lo que el SRI dijo al consultar el RUC: se enseña como aviso al guardar.
        self.avisos: List[str] = []
        #: Lo que se completó solo, para poder decirlo.
        self.completados: List[str] = []
        for campo in sri_datos.CAMPOS_AUTOMATICOS:
            if campo not in self.fields:
                continue
            self.fields[campo].required = False
            ayuda = self.fields[campo].help_text or ""
            self.fields[campo].help_text = (
                "Lo dice el SRI al indicar el RUC. " + ayuda
            ).strip()

    def clean(self) -> Dict[str, Any]:
        datos = super().clean()
        ruc = (datos.get("ruc") or "").strip()
        if not ruc:
            return datos

        if datos.get("consultar_sri"):
            self._traer_del_sri(ruc, datos)
        elif self._falta_la_razon_social(datos):
            self.add_error(
                "razon_social",
                "Escriba la razón social o marque «Traer los datos del RUC del SRI».",
            )
        return datos

    def _falta_la_razon_social(self, datos: Dict[str, Any]) -> bool:
        return not (datos.get("razon_social") or "").strip() and not self.instance.razon_social

    def _traer_del_sri(self, ruc: str, datos: Dict[str, Any]) -> None:
        """Consulta el RUC y completa lo que falte, sin pisar lo ya escrito."""
        try:
            resultado = sri_datos.consultar_datos(ruc)
        except ErrorFacturacion as exc:
            self.add_error("ruc", f"No se pudo consultar el RUC en el SRI: {exc}")
            return

        if not resultado.encontrado:
            self.add_error("ruc", f"El SRI no devolvió datos para el RUC {ruc}.")
            return

        for campo, valor in sri_datos.mapear_datos(resultado.datos).items():
            if campo not in self.fields:
                continue
            actual = datos.get(campo)
            vacio = actual in (None, "") or (isinstance(actual, str) and not actual.strip())
            if vacio and valor:
                datos[campo] = valor
                # Se deja en el formulario tal cual quedaría, para repintarlo lleno.
                self.initial[campo] = valor
                self.fields[campo].initial = valor
                self.completados.append(self.fields[campo].label)
        self.avisos.extend(resultado.avisos)


class FormularioSRI(forms.ModelForm):
    """Paso 2: dónde y con qué serie se emite."""

    class Meta:
        model = ConfiguracionEmisor
        fields = ("nombre", "ambiente", "estab", "pto_emi", "activo")
        labels = {
            "nombre": "Nombre de la configuración",
            "ambiente": "Ambiente",
            "estab": "Establecimiento",
            "pto_emi": "Punto de emisión",
            "activo": "Usar esta configuración",
        }
        widgets = {
            "nombre": forms.TextInput(attrs=caja(icono="tag")),
            "ambiente": forms.Select(attrs=desplegable(icono="map")),
            "estab": forms.TextInput(attrs=caja(icono="pin", maxlength=3)),
            "pto_emi": forms.TextInput(attrs=caja(icono="pin", maxlength=3)),
            "activo": forms.CheckboxInput(),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.avisos: List[str] = []


class FormularioSecuencial(forms.Form):
    """Una fila de la tabla de secuenciales: por dónde va la numeración.

    La serie, el ambiente y el tipo de comprobante no se tocan aquí (los pone la
    configuración: van ocultos); lo único editable es el último número usado. No
    es un ModelForm a propósito: las filas que todavía no existen en la base se
    crean al guardar, y así se ve claro cuál es cuál.
    """

    tipo_comprobante = forms.ChoiceField(
        choices=TipoComprobante.choices, widget=forms.HiddenInput()
    )
    estab = forms.CharField(max_length=3, widget=forms.HiddenInput())
    pto_emi = forms.CharField(max_length=3, widget=forms.HiddenInput())
    ambiente = forms.IntegerField(widget=forms.HiddenInput())
    ultimo = forms.IntegerField(
        label="Último número usado",
        min_value=0,
        widget=forms.TextInput(attrs=numero(min="0", step="1")),
        error_messages={
            "required": "Escriba por dónde va la numeración.",
            "invalid": "Escriba un número entero.",
            "min_value": "El último número no puede ser negativo.",
        },
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        tipo = (self.initial or {}).get("tipo_comprobante") or ""
        #: El nombre del comprobante, para rotular la fila en la plantilla.
        self.etiqueta = dict(TipoComprobante.choices).get(tipo, tipo)
        #: Cómo queda el número del próximo comprobante, con lo que se haya escrito.
        try:
            ultimo = int(self["ultimo"].value() or 0)
        except (TypeError, ValueError):
            ultimo = 0
        self.siguiente = ultimo + 1


#: El conjunto de filas: una por tipo de comprobante.
FormularioSecuenciales = forms.formset_factory(
    FormularioSecuencial, extra=0, can_delete=False
)


class FormularioCertificado(forms.ModelForm):
    """Paso 3: el archivo de firma y su contraseña.

    Al guardar se abre el ``.p12`` con la contraseña antes de dar nada por bueno:
    si la clave no es la suya, o el certificado está vencido, se dice aquí y no al
    emitir la primera factura. La contraseña se guarda cifrada (lo hace el modelo).
    """

    clave_certificado = forms.CharField(
        label="Contraseña del certificado",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs=caja(icono="key", autocomplete="new-password"),
        ),
    )

    class Meta:
        model = ConfiguracionEmisor
        fields = ("certificado",)
        labels = {"certificado": "Archivo de firma (.p12 o .pfx)"}
        widgets = {
            "certificado": forms.ClearableFileInput(
                attrs={"accept": ",".join(f".{extension}" for extension in EXTENSIONES_CERTIFICADO)}
            )
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.avisos: List[str] = []
        self.guardada = bool(self.instance.pk and self.instance.clave_certificado_cifrada)
        if self.guardada:
            self.fields["clave_certificado"].help_text = (
                "Ya hay una contraseña guardada. Déjela vacía para conservarla."
            )
        else:
            self.fields["clave_certificado"].help_text = (
                "La del archivo .p12. Se guarda cifrada."
            )

    def clean(self) -> Dict[str, Any]:
        datos = super().clean()
        archivo = datos.get("certificado")
        clave = (datos.get("clave_certificado") or "").strip()
        tiene_guardado = bool(self.instance.pk and self.instance.certificado)

        if not archivo and not tiene_guardado:
            self.add_error("certificado", "Adjunte el archivo de firma (.p12 o .pfx).")
            return datos
        if not archivo and not clave:
            return datos  # nada que cambiar: se conserva lo que había

        self._revisar(archivo, clave)
        return datos

    def _revisar(self, archivo: Any, clave: str) -> None:
        """Abre el certificado en memoria, como se hará al firmar."""
        candidato = ConfiguracionEmisor(
            ruc=self.instance.ruc,
            razon_social=self.instance.razon_social,
            dir_matriz=self.instance.dir_matriz,
            certificado=archivo or self.instance.certificado,
        )
        if not clave and self.guardada:
            try:
                clave = self.instance.obtener_clave()
            except ErrorFacturacion as exc:
                self.add_error(
                    "clave_certificado",
                    f"No se pudo leer la contraseña guardada ({exc}). Escríbala otra vez.",
                )
                return
        try:
            candidato.establecer_clave(clave)
            certificado = candidato.certificado_obj()
        except ErrorFacturacion as exc:
            self.add_error("clave_certificado", f"No se pudo abrir el certificado: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - falta la clave de cifrado, etc.
            self.add_error("certificado", f"No se pudo preparar el certificado: {exc}")
            return

        dias = certificado.dias_restantes()
        if dias is not None and dias <= 30:
            self.avisos.append(
                f"El certificado vence en {dias} día(s): renuévelo antes de esa fecha."
            )
        ruc_del_certificado = candidato.ruc_del_certificado()
        if ruc_del_certificado and self.instance.ruc and ruc_del_certificado != self.instance.ruc:
            self.avisos.append(
                f"El RUC del certificado ({ruc_del_certificado}) no es el del emisor "
                f"({self.instance.ruc})."
            )

    def save(self, commit: bool = True) -> ConfiguracionEmisor:
        objeto = super().save(commit=False)
        clave = (self.cleaned_data.get("clave_certificado") or "").strip()
        if clave:
            objeto.establecer_clave(clave)
        if commit:
            objeto.save()
        return objeto


class FormularioLogo(forms.ModelForm):
    """El logo que sale en el RIDE.

    No es un dato fiscal: es la marca de la casa. Se valida la extensión y el peso
    para que nadie suba una foto de 12 MB que luego hay que imprimir.
    """

    class Meta:
        model = LogoEmisor
        fields = ("imagen",)
        widgets = {
            "imagen": forms.ClearableFileInput(
                attrs={"accept": ",".join(f".{extension}" for extension in EXTENSIONES_LOGO)}
            )
        }

    def clean_imagen(self) -> Any:
        archivo = self.cleaned_data.get("imagen")
        if archivo and getattr(archivo, "size", 0) > TAMANO_MAXIMO_LOGO:
            megas = TAMANO_MAXIMO_LOGO // (1024 * 1024)
            raise forms.ValidationError(
                f"El logo no puede pasar de {megas} MB. Redúzcalo un poco."
            )
        return archivo
