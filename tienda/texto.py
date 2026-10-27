"""El texto enriquecido de la tienda: Markdown que se publica ya limpio.

La descripción larga de un producto se escribe en Markdown —títulos, negritas,
listas, tablas y enlaces— y se convierte a HTML al mostrarla. Antes de entregarla se
limpia con una lista blanca de etiquetas: lo que se escriba en el editor no puede
meter un guion ni un formulario en la tienda.
"""

from __future__ import annotations

import re

import bleach
import markdown
from django.utils.safestring import SafeString, mark_safe

__all__ = ["markdown_a_html"]

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

#: Los atributos que se dejan. Nada de estilos ni de guiones.
ATRIBUTOS = {
    "a": ["href", "title", "rel", "target"],
    "th": ["align"],
    "td": ["align"],
}

#: Los enlaces que se permiten.
ESQUEMAS = ("http", "https", "mailto")

#: Los bloques que se van con todo lo de dentro. ``bleach`` quita la etiqueta pero
#: deja el texto, y el comprador acabaría leyendo el guion del que lo escribió.
BLOQUES = re.compile(r"(?is)<(script|style|iframe|object)\b.*?</\1\s*>")


def markdown_a_html(texto: str) -> SafeString:
    """Convierte Markdown en HTML y lo entrega listo para la plantilla.

    Si el texto viene vacío, devuelve una cadena vacía. El resultado ya está
    saneado: ``|safe`` en la plantilla no abre la puerta a nada.
    """
    if not (texto or "").strip():
        return mark_safe("")
    html = markdown.markdown(
        texto,
        extensions=["tables", "sane_lists", "nl2br"],
        output_format="html",
    )
    sin_guiones = BLOQUES.sub("", html)
    limpio = bleach.clean(
        sin_guiones,
        tags=ETIQUETAS,
        attributes=ATRIBUTOS,
        protocols=ESQUEMAS,
        strip=True,
    )
    return mark_safe(limpio)
