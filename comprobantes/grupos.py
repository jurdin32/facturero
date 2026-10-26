"""Las cabeceras repetibles con sus filas dentro.

Una guía se entrega a varios destinatarios y cada uno lleva sus bienes; una retención
cubre varios documentos del proveedor y cada uno lleva el IVA que trae y lo que se le
retiene. Django no anida formularios solo, así que aquí se arma a mano: un formset
para las cabeceras y, por cada una, sus formsets con el prefijo de su posición
(``hijo-0-bienes``, ``hijo-1-bienes``…).

En la hoja las cabeceras se ven como una tabla —una fila por cabecera, con lo suyo en
corto— y lo que se escribe de cada una vive en un bloque escondido de la misma hoja,
que el navegador lleva a su ventana y devuelve al cerrarla: así los campos no salen del
formulario y la hoja no se llena de campos.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from django.db import transaction
from django.forms import inlineformset_factory
from django.utils.formats import date_format

#: La marca que se sustituye por el número de la cabecera (y, dentro, por el de la fila).
MARCA = "__prefix__"

#: Las cabeceras y las filas de más que trae cada tabla. Las añade el navegador desde su
#: ventana, así que no se pide ninguna de más.
EXTRA = 0


def texto(campo: Optional[Any]) -> str:
    """Cómo se lee el valor de un campo en la fila de la tabla.

    Las listas (el motivo del traslado, el tipo de documento) se leen por su nombre y
    las fechas a la manera de aquí; lo demás, tal cual viene.
    """
    if campo is None:
        return ""
    valor = campo.value()
    if valor in (None, ""):
        return ""
    for clave, etiqueta in dict(getattr(campo.field, "choices", None) or ()).items():
        if str(clave) == str(valor):
            return str(etiqueta)
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return date_format(valor, "d/m/Y")
    return str(valor)


def cuantas(conjunto: Any) -> int:
    """Las filas que quedan en una tabla, sin contar las que se están quitando."""
    return sum(
        1
        for form in conjunto.forms
        if not (form.data and form.data.get(f"{form.prefix}-DELETE"))
    )


def _visibles(documento: Any) -> tuple[str, ...]:
    """Si el comprobante no dice qué enseñar, se enseña lo que tiene a la vista."""
    return tuple(
        campo.name
        for campo in documento.hijo()
        if not campo.is_hidden and campo.name != "DELETE"
    )


class Grupo:
    """Una cabecera repetible (el destinatario, el documento del proveedor)."""

    def __init__(
        self,
        form: Any,
        hijos: list[tuple[str, str, int, Any]],
        prefijo: str,
        resumen: tuple[str, ...] = (),
    ) -> None:
        self.form = form
        #: Las filas que van dentro: (nombre, título, cuántas, formset).
        self.hijos = hijos
        self.prefijo = prefijo
        #: Los campos de la cabecera que se ven en su fila de la tabla.
        self.resumen = resumen
        self.borrado = bool(form.data.get(f"{prefijo}-DELETE")) if form.data else False

    @property
    def nombre(self) -> str:
        """Lo que se lee en la barra del buscador: el nombre de la otra parte."""
        for campo in self.form:
            if campo.field.widget.attrs.get("buscador"):
                return str(campo.value() or "")
        return ""

    @property
    def resumen_datos(self) -> list[tuple[str, str]]:
        """Lo que enseña su fila: cada columna con su campo y cómo se lee el valor."""
        return [
            (nombre, texto(self.form[nombre] if nombre in self.form.fields else None))
            for nombre in self.resumen
        ]

    @property
    def valido(self) -> bool:
        # Lo que se está quitando no se revisa: da igual cómo haya quedado escrito.
        if self.borrado:
            return True
        return self.form.is_valid() and all(
            conjunto.is_valid() for _, _, _, conjunto in self.hijos
        )

    @property
    def con_fallos(self) -> bool:
        """Si lo que se envió tiene algo mal en esta cabecera o en sus filas.

        Sin datos que revisar —la hoja recién abierta— no hay nada en rojo. Y lo
        que falla se dice en la tabla, porque casi siempre está dentro de su
        ventana, que es la que no se ve.
        """
        if not self.form.is_bound or self.borrado:
            return False
        if self.form.errors:
            return True
        return any(
            conjunto.non_form_errors() or any(fila.errors for fila in conjunto.forms)
            for _, _, _, conjunto in self.hijos
        )


class Grupos:
    """Las cabeceras de un comprobante, cada una con sus filas dentro."""

    def __init__(self, documento: Any, datos: Any, padre: Any) -> None:
        fabrica = inlineformset_factory(
            documento.modelo,
            documento.hijo_modelo,
            form=documento.hijo,
            extra=EXTRA,
            can_delete=True,
        )
        self.documento = documento
        #: Los campos que se ven en cada fila de la tabla, en orden.
        self.resumen: tuple[str, ...] = tuple(documento.resumen) or _visibles(documento)
        self.formset = fabrica(datos, instance=padre, prefix="hijo")
        self.grupos: list[Grupo] = [
            self._grupo(form, datos, f"hijo-{indice}")
            for indice, form in enumerate(self.formset.forms)
        ]

    def _grupo(self, form: Any, datos: Any, prefijo: str) -> Grupo:
        """Una cabecera con sus tablas dentro, ya contadas."""
        hijos = [
            (nombre, titulo, cuantas(conjunto), conjunto)
            for nombre, titulo, conjunto in self._filas(datos, form, prefijo)
        ]
        return Grupo(form, hijos, prefijo, self.resumen)

    def _filas(self, datos: Any, form: Any, prefijo: str) -> list[tuple[str, str, Any]]:
        """Las tablas de una cabecera, con el prefijo de su posición."""
        return [
            (
                nombre,
                titulo,
                fabrica(datos, instance=form.instance, prefix=f"{prefijo}-{nombre}"),
            )
            for nombre, fabrica, titulo in self.documento.hijos_filas
        ]

    @property
    def columnas(self) -> list[tuple[str, str]]:
        """Las columnas de la tabla: cómo se llama cada una y de qué campo sale."""
        campos = self.formset.empty_form
        cortos = self.documento.titulos_cortos
        return [
            (cortos.get(nombre) or campos[nombre].label, nombre)
            for nombre in self.resumen
            if nombre in campos.fields
        ]

    @property
    def titulos(self) -> list[tuple[str, str, str]]:
        """Las tablas de dentro: (nombre, cómo se llama, cómo se llama en la tabla)."""
        cortos = self.documento.titulos_cortos
        return [
            (nombre, titulo, cortos.get(nombre) or titulo)
            for nombre, _, titulo in self.documento.hijos_filas
        ]

    @property
    def en_blanco(self) -> Grupo:
        """La cabecera en blanco que el navegador clona, con la marca del prefijo puesta.

        Se arma con los formularios de ``muestras`` (``hijo-__prefix__-bienes``), que es
        lo que el navegador numera al añadir otra.
        """
        hijos = [
            (nombre, titulo, cuantas(conjunto), conjunto)
            for nombre, titulo, conjunto in muestras(self.documento)
        ]
        return Grupo(self.formset.empty_form, hijos, f"hijo-{MARCA}", self.resumen)

    @property
    def valido(self) -> bool:
        return self.formset.is_valid() and all(grupo.valido for grupo in self.grupos)

    def save(self) -> None:
        """Guarda todo de una vez: las cabeceras y, dentro de cada una, sus filas."""
        with transaction.atomic():
            self.formset.save()
            for grupo in self.grupos:
                if grupo.borrado:
                    continue
                for _, _, _, conjunto in grupo.hijos:
                    conjunto.instance = grupo.form.instance
                    conjunto.save()


def muestras(documento: Any) -> list[tuple[str, str, Any]]:
    """Un formulario en blanco de cada tabla, para clonar filas en el navegador.

    Se arma con la marca del prefijo puesta (``hijo-__prefix__-bienes``), que el
    JavaScript sustituye por la cabecera y la fila que toquen.
    """
    return [
        (
            nombre,
            titulo,
            fabrica(None, instance=documento.hijo_modelo(), prefix=f"hijo-{MARCA}-{nombre}"),
        )
        for nombre, fabrica, titulo in documento.hijos_filas
    ]


def hay_grupos(documento: Any) -> bool:
    """Si el comprobante se repite por cabeceras con filas dentro."""
    return bool(getattr(documento, "hijos_filas", ()))
