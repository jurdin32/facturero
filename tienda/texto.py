"""El texto enriquecido de la tienda: lo que se escribe en el editor, ya limpio.

La descripción larga de un producto se escribe en un editor visual —títulos,
negritas, listas, tablas y enlaces— y se guarda en HTML. Al mostrarla se limpia con
una lista blanca de etiquetas: lo que se escriba en el editor no puede meter un
guion ni un formulario en la tienda.
"""

from __future__ import annotations

import re

import bleach
import markdown
from django.utils.safestring import SafeString, mark_safe

__all__ = ["a_html", "html_limpio", "markdown_a_html"]

#: Lo que puede salir de una descripción. Las tablas, porque se piden; las imágenes
#: no, que para las fotos está la galería del producto.
ETIQUETAS = (
    "p", "br", "hr",
    "strong", "b", "em", "i", "del", "s", "code", "pre", "blockquote",
    "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "a",
)

#: Los atributos que se dejan. Nada de estilos ni de guiones. ``rowspan`` y
#: ``colspan`` van porque el editor deja unir celdas.
ATRIBUTOS = {
    "a": ["href", "title", "rel", "target"],
    "th": ["align", "rowspan", "colspan", "width"],
    "td": ["align", "rowspan", "colspan", "width"],
}

#: Lo más que puede abarcar una celda unida: más que eso solo puede venir de un
#: texto manipulado a mano, y rompería la tabla en la ficha.
UNION_MAXIMA = 50

#: Los enlaces que se permiten.
ESQUEMAS = ("http", "https", "mailto")

#: Los bloques que se van con todo lo de dentro. ``bleach`` quita la etiqueta pero
#: deja el texto, y el comprador acabaría leyendo el guion del que lo escribió.
BLOQUES = re.compile(r"(?is)<(script|style|iframe|object)\b.*?</\1\s*>")

#: Un párrafo que no dice nada: lo que deja el editor al pulsar Enter de más.
PARRAFO_VACIO = re.compile(r"(?is)<p>(?:\s|<br\s*/?>)*</p>")

#: Lo que deja una descripción con algo aunque no tenga ni una palabra.
CON_BULTO = re.compile(r"(?is)<(?:table|img|video|hr)\b")

#: Una línea de una tabla escrita a mano con una sola columna: ``| Directa |``.
FILA_UNICA = re.compile(r"^\s*\|\s*([^|\n]+?)\s*\|\s*$")
SEPARADORA_UNICA = re.compile(r"^\s*\|\s*:?-{1,}:?\s*\|\s*$")


def _tablas_de_una_columna_como_lista(texto: str) -> str:
    """Una tabla de una sola columna no es una tabla para Markdown.

    Al pegar la ficha de un producto se cuela así —la etiqueta en un renglón y el
    valor en el siguiente—, y Markdown la dejaba tal cual: el comprador acababa
    leyendo las barras. Se pasa a una lista, que es como se lee.
    """
    lineas = texto.split("\n")
    salida: list[str] = []
    i = 0
    while i < len(lineas):
        fila = FILA_UNICA.match(lineas[i])
        siguiente = lineas[i + 1] if i + 1 < len(lineas) else ""
        if not (fila and SEPARADORA_UNICA.match(siguiente)):
            salida.append(lineas[i])
            i += 1
            continue
        # Un bloque de una columna: la cabecera y sus filas, todas con dos barras.
        salida.append("- " + fila.group(1))
        i += 2
        while i < len(lineas):
            otra = FILA_UNICA.match(lineas[i])
            if not otra:
                break
            salida.append("- " + otra.group(1))
            i += 1
    return "\n".join(salida)


#: Lo que delata que un texto ya viene en HTML y no en Markdown.
ES_HTML = re.compile(r"<\s*(p|div|br|table|h[2-6]|ul|ol|li|strong|em|blockquote|pre)\b", re.I)


def _atributo_permitido(etiqueta: str, nombre: str, valor: str) -> bool:
    """Los atributos de la lista blanca, y los números de la tabla con sus topes."""
    limpio = (valor or "").strip()
    if nombre in ("rowspan", "colspan"):
        return limpio.isdigit() and 1 <= int(limpio) <= UNION_MAXIMA
    if nombre == "width":
        # El ancho de una columna, en porcentaje: 25% (o 25, que es lo mismo).
        if limpio.endswith("%"):
            limpio = limpio[:-1]
        return limpio.isdigit() and 1 <= int(limpio) <= 100
    return nombre in ATRIBUTOS.get(etiqueta, ())


def _limpiar(html: str) -> str:
    """Pasa la lista blanca y quita los párrafos que no dicen nada."""
    limpio = bleach.clean(
        html,
        tags=ETIQUETAS,
        attributes=_atributo_permitido,
        protocols=ESQUEMAS,
        strip=True,
    )
    limpio = PARRAFO_VACIO.sub("", limpio).strip()
    if not re.sub(r"<[^>]+>", "", limpio).strip() and not CON_BULTO.search(limpio):
        return ""
    return limpio


def html_limpio(texto: str) -> SafeString:
    """Sanea el HTML que escribió el dueño de la tienda antes de publicarlo.

    El editor ya entrega HTML; aquí se le quitan los guiones y lo que no sea de la
    lista blanca, para que ``|safe`` en la plantilla no abra la puerta a nada.
    """
    return mark_safe(_limpiar(BLOQUES.sub("", texto or "")))


def a_html(texto: str) -> SafeString:
    """El texto de la descripción, listo para la ficha.

    Lo que se escribe hoy es HTML —el editor es visual—, pero las descripciones
    anteriores se escribieron en Markdown: las que no traen etiquetas se siguen
    convirtiendo, para no dejar a nadie con las marcas a la vista.
    """
    if not (texto or "").strip():
        return mark_safe("")
    if ES_HTML.search(texto):
        return html_limpio(texto)
    return markdown_a_html(texto)


def markdown_a_html(texto: str) -> SafeString:
    """Convierte Markdown en HTML y lo entrega listo para la plantilla.

    Si el texto viene vacío, devuelve una cadena vacía. El resultado ya está
    saneado: ``|safe`` en la plantilla no abre la puerta a nada.
    """
    if not (texto or "").strip():
        return mark_safe("")
    html = markdown.markdown(
        _tablas_de_una_columna_como_lista(texto),
        extensions=["tables", "sane_lists", "nl2br"],
        output_format="html",
    )
    return mark_safe(_limpiar(BLOQUES.sub("", html)))
