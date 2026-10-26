"""Datos complementarios del catastro del SRI.

El servicio de ``ConsultaRuc`` devuelve la razón social, el estado y el régimen,
pero no la dirección. La dirección matriz está en otro servicio público del SRI
(``Establecimiento/consultarPorNumeroRuc``), que es el que usa su propia página
de consulta.
"""

from __future__ import annotations

import logging

import requests

__all__ = ["direccion_matriz"]

URL_ESTABLECIMIENTOS = (
    "https://srienlinea.sri.gob.ec/sri-catastro-sujeto-servicio-internet/rest/"
    "Establecimiento/consultarPorNumeroRuc"
)

_CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-EC,es;q=0.9",
    "Referer": (
        "https://srienlinea.sri.gob.ec/sri-en-linea/SriRucWeb/ConsultaRuc/"
        "Consultas/consultaRuc"
    ),
}


def direccion_matriz(ruc: str, *, timeout: float = 6.0) -> str:
    """La dirección del establecimiento matriz, si el SRI la publica."""
    try:
        respuesta = requests.get(
            URL_ESTABLECIMIENTOS,
            params={"numeroRuc": ruc},
            headers=_CABECERAS,
            timeout=timeout,
        )
        respuesta.raise_for_status()
        establecimientos = respuesta.json()
    except (requests.RequestException, ValueError) as error:
        logging.getLogger(__name__).warning(
            "No se pudo consultar la dirección del RUC %s: %s", ruc, error
        )
        return ""

    if not isinstance(establecimientos, list):
        return ""
    matriz = next(
        (fila for fila in establecimientos if str(fila.get("matriz", "")).upper() == "SI"),
        None,
    )
    fila = matriz or (establecimientos[0] if establecimientos else {})
    return str(fila.get("direccionCompleta") or "").strip()
