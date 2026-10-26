"""El papel: todo lo que se imprime se escribe en HTML.

Los PDF de la aplicación —los reportes, el acta de cierre y los vales de caja— se
arman con **plantillas HTML** y la hoja de estilo ``static/css/papel.css``, y
WeasyPrint las convierte en PDF. Así lo que se ve en pantalla y lo que se firma
hablan el mismo idioma y no hay dos maquetaciones que mantener.

El logo viaja dentro del HTML como ``data:`` (una imagen en línea), para que el
documento no dependa de rutas del disco: se genera igual desde la aplicación, desde
un test o desde un script.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Any, Optional

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string

__all__ = ["a_pdf", "data_uri", "hoja_de_estilo", "logo_en_linea", "papel"]


@lru_cache(maxsize=1)
def hoja_de_estilo() -> str:
    """El CSS de los papeles, tal cual está en ``static/css/papel.css``."""
    ruta = finders.find("css/papel.css")
    if not ruta:
        return ""
    with open(ruta, encoding="utf-8") as archivo:
        return archivo.read()


def data_uri(contenido: bytes, tipo: str = "image/png") -> str:
    """La imagen metida en una dirección ``data:`` para llevarla dentro del HTML."""
    return f"data:{tipo};base64,{base64.b64encode(contenido).decode('ascii')}"


def logo_en_linea() -> Optional[str]:
    """El logo de los papeles —el del emisor o el de Factiz— listo para el HTML."""
    try:
        from reportes.marca import logo_de_los_reportes

        encontrado = logo_de_los_reportes()
        if not encontrado:
            return None
        contenido, extension = encontrado
        return data_uri(contenido, f"image/{'jpeg' if extension == 'jpg' else extension}")
    except Exception:  # noqa: BLE001 - un logo roto no puede tumbar el papel
        return None


def a_pdf(html: str) -> bytes:
    """El HTML convertido en PDF."""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


def papel(plantilla: str, contexto: dict[str, Any]) -> bytes:
    """Pinta esa plantilla con ese contexto y la devuelve en PDF."""
    datos = {"hoja": hoja_de_estilo(), **contexto}
    return a_pdf(render_to_string(plantilla, datos))
