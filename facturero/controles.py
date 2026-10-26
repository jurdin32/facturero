"""Los atributos que convierten los campos de un formulario en controles de Metro.

Metro monta sus cajas de texto, desplegables y casillas a partir de un `data-role`
y de unos cuantos `data-*` más (el icono de delante, el botón de borrar…). Escribir
esos atributos a mano en cada `widgets = {...}` de cada formulario es pedir que se
olvide alguno, así que se piden aquí.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms

__all__ = ["CampoImporte", "NumeroImporte", "caja", "de_fecha", "desplegable", "fecha", "numero"]


def _icono(nombre: str | None) -> str | None:
    """El icono que Metro enseña dentro de la caja, a la izquierda."""
    return f"<span class='mif-{nombre}'></span>" if nombre else None


def _limpio(attrs: dict[str, Any]) -> dict[str, Any]:
    """Sin los huecos: a los `data-*` de Metro no les sienta bien el vacío."""
    return {clave: valor for clave, valor in attrs.items() if valor not in (None, "")}


def caja(
    *,
    icono: str | None = None,
    tipo: str | None = None,
    clase: str | None = None,
    limpia: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Una caja de texto de Metro.

    `icono` es el nombre sin el `mif-` (``"search"``); `tipo` sólo hace falta
    cuando no lo pone el propio widget (``"date"``, ``"search"``); `limpia` añade
    la aspita de borrar, para los buscadores.
    """
    return _limpio(
        {
            "data-role": "input",
            "data-prepend": _icono(icono),
            "data-clear-button": "true" if limpia else None,
            "type": tipo,
            "class": clase,
            **extra,
        }
    )


def fecha(*, clase: str | None = None, **extra: Any) -> dict[str, Any]:
    """Un campo de fecha, sin el componente de Metro.

    El envoltorio de Metro le come al campo el icono del calendario que dibuja el
    navegador, y una fecha no lleva icono de delante ni aspa de borrar, así que
    se queda con la caja de la casa, que es la misma.

    El ``type`` no va aquí: Django pinta el suyo el primero y el navegador se queda
    con ese, así que acabaría siendo una caja de texto. Lo pone `de_fecha`.
    """
    return _limpio(
        {
            "class": f"campo-fecha {clase}".strip() if clase else "campo-fecha",
            **extra,
        }
    )


def de_fecha(campo: forms.Field) -> forms.Field:
    """Deja un campo de fecha con el calendario del navegador.

    Hay que tocar el widget y no solo sus atributos: Django escribe su
    ``type="text"`` delante de los demás, y el navegador se queda con el primero.

    Y el valor va como lo entiende el calendario del navegador (``2026-10-26``), no
    como se lee aquí: con la fecha escrita a la española el navegador no la reconoce
    y deja la caja vacía, que es como se perdían las fechas al volver a abrir un
    borrador.
    """
    if hasattr(campo.widget, "input_type"):
        campo.widget.input_type = "date"
    campo.widget.format = "%Y-%m-%d"
    campo.widget.attrs.update(fecha())
    # Lo que llega puede venir del calendario (2026-10-26) o escrito a mano aquí.
    if isinstance(campo, forms.DateField):
        campo.input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
    return campo


def numero(*, icono: str | None = None, clase: str | None = None, **extra: Any) -> dict[str, Any]:
    """Una caja para importes y cantidades, con el teclado de números."""
    return caja(
        icono=icono,
        clase=f"campo-num {clase}".strip() if clase else "campo-num",
        inputmode="decimal",
        autocomplete="off",
        **extra,
    )


def desplegable(*, icono: str | None = None, clase: str | None = None, **extra: Any) -> dict[str, Any]:
    """Un desplegable de Metro."""
    return _limpio(
        {
            "data-role": "select",
            "data-prepend": _icono(icono),
            "class": clase,
            **extra,
        }
    )


class NumeroImporte(forms.TextInput):
    """Un importe se enseña como se escribe: sin ceros de relleno y con la coma.

    En la base el paquete guarda seis decimales (``10.000000``); enseñarlos tal cual
    en la hoja hace que el comprobante parezca un volcado de la base.
    """

    def format_value(self, valor: Any) -> str:
        if valor in (None, ""):
            return ""
        try:
            numero_decimal = Decimal(valor)
        except (InvalidOperation, TypeError, ValueError):
            # Lo que no es un número se enseña tal cual: si alguien escribió una
            # letra, tiene que volver a verla para corregirla.
            return str(valor)
        texto = f"{numero_decimal:f}"
        if "." in texto:
            texto = texto.rstrip("0").rstrip(".")
        return texto.replace(".", ",")


class CampoImporte(forms.DecimalField):
    """Cantidades y precios escritos como se dicen.

    En Ecuador el decimal va con coma y el millar con punto: aquí se aceptan
    «1.234,56», «1234,56» y «1234.56», y el número llega limpio al modelo. Un campo
    que solo entendiera el punto haría que el primer cliente que escriba «10,50»
    reciba un error rojo, que es justo lo que no queremos.
    """

    #: Se escribe a mano. Con el ``type=number`` del navegador la coma no entra, y
    #: en Ecuador el decimal se escribe con coma.
    widget = NumeroImporte

    def to_python(self, valor: Any) -> Any:
        if isinstance(valor, str):
            texto = valor.strip().replace(" ", "").replace("$", "")
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            valor = texto or None
        return super().to_python(valor)
