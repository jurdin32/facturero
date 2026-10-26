"""Los colores de Metro para cada estado del comprobante y de los movimientos.

Metro tiene sus chips (``chip success``, ``chip alert``…) y aquí se decide cuál le
toca a cada estado, para no repartir esa correspondencia por las plantillas.
"""

from __future__ import annotations

from factec.django.models import EstadoComprobante

#: Estado (del comprobante o del movimiento) → clases del chip de Metro.
COLORES: dict[str, str] = {
    # Comprobantes del SRI.
    EstadoComprobante.AUTORIZADO: "success soft",
    EstadoComprobante.DEVUELTO: "alert soft",
    EstadoComprobante.NO_AUTORIZADO: "alert soft",
    EstadoComprobante.ERROR: "alert",
    EstadoComprobante.FIRMADO: "warning soft",
    EstadoComprobante.RECIBIDO: "info soft",
    EstadoComprobante.EN_PROCESO: "info soft",
    EstadoComprobante.BORRADOR: "",
    # Movimientos de inventario.
    "entrada": "success soft",
    "salida": "alert soft",
    "ajuste": "warning soft",
    "devolucion": "info soft",
    "factura": "",
    # Productos retirados.
    "retirado": "",
}

#: Estados en los que el comprobante va por el SRI: giran, para que se vea.
EN_MARCHA = (
    EstadoComprobante.FIRMADO,
    EstadoComprobante.RECIBIDO,
    EstadoComprobante.EN_PROCESO,
)

#: Tanto la etiqueta del SRI como el valor interno llevan al valor interno.
POR_ETIQUETA: dict[str, str] = {estado.label: estado.value for estado in EstadoComprobante}
POR_ETIQUETA.update({estado.value: estado.value for estado in EstadoComprobante})

#: Del estado del comprobante al avance del ciclo, para la barra de progreso.
AVANCE: dict[str, int] = {
    "SIN EMITIR": 0,
    EstadoComprobante.BORRADOR: 10,
    EstadoComprobante.FIRMADO: 40,
    EstadoComprobante.RECIBIDO: 70,
    EstadoComprobante.EN_PROCESO: 80,
    EstadoComprobante.AUTORIZADO: 100,
    EstadoComprobante.DEVUELTO: 100,
    EstadoComprobante.NO_AUTORIZADO: 100,
    EstadoComprobante.ERROR: 100,
}

#: Las etapas que enseña la barra del ciclo de vida.
ETAPAS = ("Emitida", "Firmada", "Recibida", "Autorizada")


def _valor(estado: object) -> str:
    """El valor interno del estado, venga como valor o como etiqueta.

    Las plantillas pasan unas veces uno y otras veces la otra («AUTORIZADO» y
    «Autorizado»), y los movimientos del inventario en minúsculas.
    """
    texto = str(estado)
    if texto in POR_ETIQUETA:
        return POR_ETIQUETA[texto]
    if texto.lower() in COLORES:
        return texto.lower()
    return texto.upper()


def chip(estado: object) -> str:
    """Clases del chip de Metro que le tocan a un estado."""
    clave = _valor(estado)
    return COLORES.get(clave, COLORES.get(clave.lower(), ""))


def en_marcha(estado: object) -> bool:
    """¿El comprobante está ahora mismo en manos del SRI?"""
    return _valor(estado) in EN_MARCHA


def avance(estado: object) -> int:
    """Cuánto ha avanzado el comprobante, de 0 a 100."""
    return AVANCE.get(_valor(estado), 0)


def clase_avance(estado: object) -> str:
    """De qué color va la barra del ciclo: verde, rojo, ámbar o el de la casa."""
    clave = _valor(estado)
    if not str(estado):
        return ""
    if clave == EstadoComprobante.AUTORIZADO:
        return "exito"
    if clave in (EstadoComprobante.DEVUELTO, EstadoComprobante.NO_AUTORIZADO, EstadoComprobante.ERROR):
        return "peligro"
    if clave in EN_MARCHA:
        return "cuidado"
    return ""


def nombre(estado: object) -> str:
    """El nombre largo del estado, no la clave interna."""
    try:
        return EstadoComprobante(estado).label
    except ValueError:
        return str(estado).replace("_", " ").capitalize()
