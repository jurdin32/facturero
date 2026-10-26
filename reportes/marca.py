"""El logo que llevan los reportes.

Manda el logo que el emisor haya cargado en «Configuración del SRI»: es su marca y
la que va en el RIDE. Si todavía no hay ninguno, el reporte sale con el logo de
Factiz, que está en ``static/img/``; y si tampoco estuviera, con el nombre de la
empresa escrito, para que el PDF nunca salga sin encabezado.

Los formatos vectoriales (SVG) no los saben leer ni el generador de PDF ni el de
Excel, así que en ese caso se usa el logo de la marca, que es de mapa de bits.
"""

from __future__ import annotations

from typing import Optional

from django.contrib.staticfiles import finders
from factec.django import conf

__all__ = ["logo_de_los_reportes"]

#: Las extensiones que sí se pueden meter en un PDF o en un Excel.
UTILES = ("png", "jpg", "jpeg", "webp")

#: Los nombres del logo de la casa, en el orden en que se buscan. El apaisado va
#: primero porque es el que entra en el encabezado de una hoja.
DE_LA_CASA = ("logo-ancho", "logo", "marca", "icono")


def _bytes_de(archivo) -> Optional[tuple[bytes, str]]:
    """El contenido del archivo y su extensión, si se puede leer."""
    try:
        nombre = getattr(archivo, "name", "") or ""
        extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        if extension not in UTILES:
            return None
        archivo.open("rb")
        try:
            return archivo.read(), extension
        finally:
            archivo.close()
    except (OSError, ValueError):
        return None


def _logo_del_emisor() -> Optional[tuple[bytes, str]]:
    from configuracion.models import LogoEmisor

    emisor = conf.configuracion_activa()
    if emisor is None:
        return None
    logo = LogoEmisor.objects.filter(emisor=emisor).first()
    if logo is None or not logo.imagen:
        return None
    return _bytes_de(logo.imagen)


def _logo_de_la_casa() -> Optional[tuple[bytes, str]]:
    for nombre in DE_LA_CASA:
        for extension in UTILES:
            encontrado = finders.find(f"img/{nombre}.{extension}")
            if not encontrado:
                continue
            try:
                with open(encontrado, "rb") as archivo:
                    return archivo.read(), extension
            except OSError:  # noqa: PERF203 - si no se puede leer, se prueba el otro
                continue
    return None


def logo_de_los_reportes() -> Optional[tuple[bytes, str]]:
    """El logo del emisor o, si no hay, el de Factiz. ``None`` si no hay ninguno."""
    return _logo_del_emisor() or _logo_de_la_casa()
