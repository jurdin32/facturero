"""Lo que comparten todos los comprobantes electrónicos en la pantalla.

Facturar, emitir una nota de crédito o una guía de remisión son la misma tarea vista
desde fuera: un documento que se firma, se envía al SRI y deja XMLs y respuestas. Lo
que cambia es qué campos se llenan; lo demás —el estado, los documentos que deja el
envío, la lectura de la clave de acceso, los totales— es igual para los seis.

Vive en la configuración del proyecto (no en una aplicación) porque lo usan la app de
facturación y la de los demás comprobantes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from factec.django.models import ComprobanteEmitido, EstadoComprobante

__all__ = [
    "DOCUMENTOS_SRI",
    "ESTADOS",
    "FORMATOS_RIDE",
    "archivos_de",
    "clave_por_partes",
    "estado_de",
    "informacion_adicional_de",
    "iva_por_tarifa",
    "subtotales_por_tarifa",
    "totales_de",
]

#: Estados con su nombre, para las etiquetas (el resto los pone el paquete).
ESTADOS = {estado.value: estado.label for estado in EstadoComprobante}

#: Los formatos de impresión del RIDE: la hoja A4 y el tíquet de 80 mm.
FORMATOS_RIDE = {
    "a4": {"nombre": "A4", "pagina": "A4", "margen": "12mm"},
    "t80": {"nombre": "Tíquet 80 mm", "pagina": "80mm auto", "margen": "3mm"},
}

#: Los documentos que deja el envío de un comprobante: de dónde sale el contenido,
#: cómo se llama el archivo y para qué sirve. La clave es la que viaja en la
#: dirección (``.../documento/<clave>/``) y el orden es el del ciclo del comprobante.
DOCUMENTOS_SRI: tuple[dict[str, Any], ...] = (
    {
        "clave": "sin-firma",
        "titulo": "XML sin firmar",
        "campo": "xml_sin_firma",
        "archivo": "sin_firma.xml",
        "tipo": "application/xml",
        "icono": "file-text",
        "ayuda": "El comprobante tal como se armó, antes de la firma electrónica.",
    },
    {
        "clave": "firmado",
        "titulo": "XML firmado",
        "campo": "xml_firmado",
        "archivo": "firmado.xml",
        "tipo": "application/xml",
        "icono": "file-binary",
        "ayuda": "Ya con la firma electrónica del emisor: es el que se envía al SRI.",
    },
    {
        "clave": "autorizado",
        "titulo": "XML autorizado",
        "campo": "xml_autorizado",
        "archivo": "autorizado.xml",
        "tipo": "application/xml",
        "icono": "check-circle-outline",
        "principal": True,
        "ayuda": "El que devolvió el SRI autorizado: es el documento con validez legal.",
    },
    {
        "clave": "respuesta-recepcion",
        "titulo": "Respuesta de recepción",
        "campo": "respuesta_recepcion",
        "archivo": "respuesta_recepcion.xml",
        "tipo": "application/xml",
        "icono": "code",
        "ayuda": "Lo que contestó el SRI al recibir el comprobante.",
    },
    {
        "clave": "respuesta-autorizacion",
        "titulo": "Respuesta de autorización",
        "campo": "respuesta_autorizacion",
        "archivo": "respuesta_autorizacion.xml",
        "tipo": "application/xml",
        "icono": "code",
        "ayuda": "Lo que contestó el SRI al autorizar el comprobante.",
    },
    {
        "clave": "error",
        "titulo": "Detalle del error",
        "campo": "error",
        "archivo": "error.txt",
        "tipo": "text/plain",
        "icono": "warning",
        "ayuda": "El detalle del último fallo de envío, tal como se produjo.",
    },
)

#: Los documentos por su clave, para servirlos desde la dirección.
DOCUMENTOS_POR_CLAVE = {documento["clave"]: documento for documento in DOCUMENTOS_SRI}


def estado_de(registro: Optional[ComprobanteEmitido]) -> str:
    """El nombre del estado del comprobante («Borrador» si no se ha emitido)."""
    if registro is None:
        return ESTADOS[EstadoComprobante.BORRADOR]
    return ESTADOS.get(registro.estado, registro.estado)


def _tamano(bytes_: int) -> str:
    """El tamaño de un archivo en una línea («12,4 kB»)."""
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} kB".replace(".", ",")
    return f"{bytes_ / (1024 * 1024):.2f} MB".replace(".", ",")


def archivos_de(registro: Optional[ComprobanteEmitido]) -> list[dict[str, Any]]:
    """Los documentos del comprobante que ya existen, listos para la pantalla.

    Cada uno trae de dónde sale (``campo``), cómo se llama su archivo y su tamaño,
    para pintarlos en la ficha y servirlos sin exponer rutas del disco.
    """
    if registro is None:
        return []
    archivos: list[dict[str, Any]] = []
    for documento in DOCUMENTOS_SRI:
        contenido = getattr(registro, documento["campo"], "") or ""
        if not contenido:
            continue
        bytes_ = len(contenido.encode("utf-8"))
        archivos.append({**documento, "bytes": bytes_, "tamano": _tamano(bytes_)})
    return archivos


def clave_por_partes(clave: str) -> list[tuple[str, str]]:
    """La clave de acceso troceada como la lee el SRI (49 dígitos).

    Es la misma información que el paquete sabe descomponer, puesta al lado para no
    tener que contar dígitos a ojo cuando algo no cuadra.
    """
    if len(clave or "") != 49:
        return []
    return [
        ("Fecha", clave[0:8]),
        ("Comprobante", clave[8:10]),
        ("RUC", clave[10:23]),
        ("Ambiente", clave[23:24]),
        ("Emisión", clave[24:25]),
        ("Serie", clave[25:31] + clave[31:34]),
        ("Secuencial", clave[34:43]),
        ("Verificador", clave[43:44]),
        ("Código", clave[44:49]),
    ]


def totales_de(documento: Any) -> dict[str, Any]:
    """Los totales del comprobante, con la suma de las líneas antes del descuento.

    El paquete devuelve lo que va al XML (``total_sin_impuestos`` ya descontado). La
    suma de las líneas —sin descontar— es la que hace que en el papel todo cuadre a
    la vista: suma − descuento = subtotal, y subtotal + IVA = total.
    """
    totales = documento.totales()
    totales["total_bruto"] = totales["total_sin_impuestos"] + totales["total_descuento"]
    return totales


def iva_por_tarifa(detalles: Any) -> list[dict[str, Any]]:
    """El IVA agrupado por tarifa, para el RIDE: base y valor de cada tipo.

    Un comprobante puede llevar líneas con IVA de 15 % y otras con 0 %: en el papel
    se desglosa cada tarifa, como lo lee el SRI.
    """
    grupos: dict[str, dict[str, Any]] = {}
    for linea in detalles:
        clave = str(linea.codigo_porcentaje_iva)
        grupo = grupos.setdefault(
            clave,
            {"tarifa": linea.tarifa_iva, "base": Decimal("0"), "valor": Decimal("0")},
        )
        grupo["base"] += linea.precio_total_sin_impuesto
        grupo["valor"] += linea.valor_iva
    # Las tarifas que no cobran IVA (0 %) no añaden nada: el subtotal ya las lleva.
    return sorted(
        (grupo for grupo in grupos.values() if grupo["valor"]),
        key=lambda grupo: grupo["tarifa"],
    )


def subtotales_por_tarifa(detalles: Any) -> list[dict[str, Any]]:
    """La base de cada tarifa, incluida la del 0 %.

    El RIDE desglosa «SUBTOTAL 15 %» y «SUBTOTAL 0 %»; el IVA de cada una va aparte,
    así que aquí sí entran las tarifas que no cobran nada.
    """
    grupos: dict[str, dict[str, Any]] = {}
    for linea in detalles:
        clave = str(linea.codigo_porcentaje_iva)
        grupo = grupos.setdefault(
            clave,
            {"tarifa": linea.tarifa_iva, "base": Decimal("0"), "valor": Decimal("0")},
        )
        grupo["base"] += linea.precio_total_sin_impuesto
        grupo["valor"] += linea.valor_iva
    return sorted(grupos.values(), key=lambda grupo: grupo["tarifa"])


def informacion_adicional_de(documento: Any) -> list[tuple[str, str]]:
    """Lo que va en «Información Adicional» del RIDE, concepto y detalle.

    Las observaciones y los campos adicionales del documento —«NOMBRE=VALOR»
    separados por punto y coma— se leen como filas, que es como los enseña el SRI.
    """
    filas: list[tuple[str, str]] = []
    observaciones = str(getattr(documento, "observaciones", "") or "").strip()
    if observaciones:
        filas.append(("Observaciones", observaciones))
    crudo = str(getattr(documento, "informacion_adicional", "") or "")
    for trozo in crudo.split(";"):
        trozo = trozo.strip()
        if not trozo:
            continue
        if "=" in trozo:
            concepto, detalle = trozo.split("=", 1)
            filas.append((concepto.strip(), detalle.strip()))
        else:
            filas.append(("Información adicional", trozo))
    return filas
