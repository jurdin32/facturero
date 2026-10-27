"""El sello de versión de los archivos estáticos propios.

Queda en todas las plantillas como ``sello_estatico`` y se pega a la dirección del
CSS y del JavaScript: ``/static/js/facturacion.js?v=1760000000``.

Hace falta porque el servidor de desarrollo no manda cabeceras de caché: el
navegador se guarda el archivo, y después de cambiarlo puede seguir sirviendo la
versión vieja (y entonces el buscador no abre, o el estilo se ve a medias, y
parece que el cambio no se hizo). El sello es la fecha del archivo más nuevo de
los propios: cambia al guardarlos y el navegador los vuelve a pedir.

Los de Metro también lo llevan: su hoja quedó recortada a lo que la aplicación
usa, sus iconos van en WOFF2 y su guion se toca al subir de versión, así que
también hay que poder cambiarlos sin que el navegador se quede con lo viejo.
"""

from __future__ import annotations

import os
from typing import Any

from django.contrib.staticfiles import finders

__all__ = ["PROPIOS", "sello", "sello_estatico"]

#: Los archivos que se tocan a mano; los terceros no hacen falta. Todos los que
#: se piden con `?v=` tienen que estar aquí: si falta uno, al cambiarlo el navegador
#: sigue con la copia vieja.
PROPIOS = (
    "css/tienda.css",
    "css/metro/metro.css",
    "js/metro/metro.js",
    "icons/core/style.css",
    "css/interfaz.css",
    "js/interfaz.js",
    "js/facturacion.js",
    "js/comprobantes.js",
    "js/consulta_ruc.js",
    "js/cliente_modal.js",
    "js/contabilidad.js",
    "js/caja.js",
    "js/editor_markdown.js",
    "js/tienda.js",
    "js/ordenar_menu.js",
    "js/imprimir.js",
    "js/bloqueo.js",
    "js/entrar.js",
)


def sello() -> int:
    """La fecha (en segundos) del más nuevo de los archivos propios, o 0."""
    fechas = []
    for nombre in PROPIOS:
        encontrado = finders.find(nombre)
        if not encontrado:
            continue
        try:
            fechas.append(int(os.path.getmtime(encontrado)))
        except OSError:  # noqa: PERF203 - un archivo que no se puede leer no rompe
            continue
    return max(fechas) if fechas else 0


def sello_estatico(request: Any) -> dict[str, int]:
    """Context processor: deja ``sello_estatico`` en todas las plantillas."""
    return {"sello_estatico": sello()}
