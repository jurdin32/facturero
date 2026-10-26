"""La imagen de marca, la que el proyecto ponga en ``static/img/``.

Se busca por nombre y da igual la extensión, así que para poner un logo basta con
dejar el fichero en ``static/img/`` con el nombre de la pantalla:

* ``entrar`` — la pantalla de entrada.
* ``bloqueo`` — la de bloqueo.
* ``marca`` — para las dos, cuando no hay una propia.
* ``fondo-entrar`` y ``fondo-bloqueo`` — la imagen que va de fondo en cada una.

Si no hay ninguna, la pantalla se queda con lo que trae de serie. El ``LEEME.txt``
de esa carpeta lo cuenta para quien vaya a poner la imagen.
"""

from __future__ import annotations

from django.contrib.staticfiles import finders
from django.template import Library
from django.templatetags.static import static

__all__ = ["imagen_marca"]

register = Library()

#: Las extensiones que se buscan, en orden. Las de mapa de bits van antes que el
#: vector a propósito: el fondo de la entrada trae un SVG de serie, y así la imagen
#: que ponga el proyecto con ese mismo nombre —en PNG o JPG— es la que se usa.
EXTENSIONES = ("png", "webp", "jpg", "jpeg", "avif", "svg")


@register.simple_tag
def imagen_marca(*nombres: str) -> str:
    """La dirección de la primera imagen que exista, o nada si no hay ninguna."""
    for nombre in nombres or ("marca",):
        for extension in EXTENSIONES:
            ruta = f"img/{nombre}.{extension}"
            if finders.find(ruta):
                return static(ruta)
    return ""
