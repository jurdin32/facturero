"""Las consultas de los reportes, todas devueltas como una tabla.

Cada función recibe el filtro del período y devuelve un ``Tabla``: el mismo dato
para la pantalla, el PDF y el Excel. Lo contable se apoya en los libros que ya
calcula ``contabilidad.informes`` —no se rehace la partida doble— y lo electrónico
se lee de los modelos del paquete ``factec``.

Los comprobantes que cuentan son los **autorizados por el SRI**: un borrador o uno
devuelto no es venta ni ingreso, y así lo pide el Reglamento de Comprobantes de
Venta, Retención y Documentos Complementarios para los registros de ventas y
compras. Las notas de crédito restan y las de débito suman.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterator, Optional, Sequence

from factec.catalogos import PORCENTAJE_IVA
from factec.django.documentos import (
    Factura,
    LiquidacionCompra,
    NotaCredito,
    NotaDebito,
    Retencion,
)
from factec.django.models import (
    ComprobanteEmitido,
    EstadoComprobante,
    TipoComprobante,
)

from contabilidad import informes
from contabilidad.models import Compra, Cuenta
from inventario.models import Movimiento, TipoMovimiento

from facturero.documentos_sri import ESTADOS

from .periodos import Filtro, anterior
from .tabla import CERO, Columna, Tabla, participacion, sumar, variacion

__all__ = [
    "balance",
    "compras",
    "comprobantes",
    "comprobantes_procesos",
    "inventario_existencias",
    "inventario_movimientos",
    "libro_diario",
    "libro_mayor",
    "resultados",
    "retenciones",
    "situacion",
    "ventas",
    "ventas_clientes",
    "ventas_por_dia",
    "ventas_por_usuario",
    "ventas_productos",
    "ventas_tarifas",
]

#: Los comprobantes que son venta, con su modelo, el campo de la otra parte y el
#: signo con el que entran en los totales (la nota de crédito resta).
CLASES_DE_VENTA: tuple[tuple[str, Any, str, int], ...] = (
    ("Factura", Factura, "receptor", 1),
    ("Nota de crédito", NotaCredito, "receptor", -1),
    ("Nota de débito", NotaDebito, "receptor", 1),
    ("Liquidación de compra", LiquidacionCompra, "proveedor", 1),
)

#: Los nombres de las tarifas de IVA que no llevan porcentaje.
SIN_TARIFA = {
    "6": "No objeto de IVA",
    "7": "Exento de IVA",
    "8": "IVA diferenciado",
}

#: Los impuestos que se retienen, por su código de la tabla del SRI.
IMPUESTOS_RETENIDOS = {"1": "Renta", "2": "IVA", "6": "ISD"}

NOTA_VENTAS = (
    "Solo entran los comprobantes autorizados por el SRI; las notas de crédito restan "
    "y las de débito suman. La base imponible se separa por tarifa de IVA y no incluye "
    "el impuesto, conforme al Reglamento de Comprobantes de Venta, Retención y "
    "Documentos Complementarios."
)


# ---------------------------------------------------------------- ayudas


def _rango(consulta: Any, filtro: Filtro, campo: str = "fecha_emision") -> Any:
    return consulta.filter(**{f"{campo}__gte": filtro.desde, f"{campo}__lte": filtro.hasta})


def documentos_de_venta(filtro: Filtro) -> Iterator[tuple[str, Any, int, str]]:
    """Los comprobantes de venta autorizados del período, con su clase y su signo."""
    for clase, modelo, campo_contraparte, signo in CLASES_DE_VENTA:
        consulta = _rango(
            modelo.objects.filter(
                comprobante__estado=EstadoComprobante.AUTORIZADO.value
            ),
            filtro,
        ).select_related(campo_contraparte, "comprobante")
        if hasattr(modelo, "detalles"):
            consulta = consulta.prefetch_related("detalles")
        for documento in consulta.order_by("fecha_emision", "secuencial", "pk"):
            yield clase, documento, signo, campo_contraparte


def _numero(documento: Any) -> str:
    comprobante = getattr(documento, "comprobante", None)
    if comprobante is not None:
        return comprobante.numero_comprobante
    return f"sin emitir · {getattr(documento, 'secuencial', '') or ''}".strip(" ·")


def _contraparte(documento: Any, campo: str) -> Any:
    return getattr(documento, campo, None)


def _total(documento: Any, signo: int) -> Decimal:
    return (documento.total or CERO) * signo


def _bases(documento: Any) -> dict[str, Decimal]:
    return informes.bases_por_tarifa(documento)


def _detalles_con_signo(filtro: Filtro) -> Iterator[tuple[Any, int, Any]]:
    """Las líneas de los comprobantes del período, con su signo y su documento."""
    for clase, documento, signo, _campo in documentos_de_venta(filtro):
        if clase == "Nota de débito":
            continue  # sin líneas: entra por su base, no por productos
        for detalle in documento.detalles.all():
            yield detalle, signo, documento


def _tarifa_de(codigo: Any) -> str:
    clave = str(codigo or "")
    if clave in SIN_TARIFA:
        return SIN_TARIFA[clave]
    return f"IVA {PORCENTAJE_IVA.get(clave, CERO)} %"


def _etiqueta_estado(codigo: str) -> str:
    return ESTADOS.get(codigo, codigo or "—")


def _horas(desde: Any, hasta: Any) -> Optional[float]:
    if not desde or not hasta:
        return None
    return (hasta - desde).total_seconds() / 3600


# ------------------------------------------------------------------ ventas


def ventas(filtro: Filtro) -> Tabla:
    """El libro de ventas: cada comprobante autorizado con sus bases y su IVA."""
    filas = []
    for clase, documento, signo, campo in documentos_de_venta(filtro):
        bases = _bases(documento)
        contraparte = _contraparte(documento, campo)
        filas.append(
            [
                clase,
                _numero(documento),
                documento.fecha_emision,
                getattr(contraparte, "identificacion", ""),
                getattr(contraparte, "razon_social", ""),
                bases["base_0"] * signo,
                bases["base_gravada"] * signo,
                bases["base_exenta"] * signo,
                bases["iva"] * signo,
                _total(documento, signo),
            ]
        )

    totales = [None, None, None, None, "Totales"] + [sumar(filas, posicion) for posicion in range(5, 10)]

    antes = anterior(filtro)
    vendido_antes = sum((_total(doc, signo) for _c, doc, signo, _f in documentos_de_venta(antes)), CERO)
    vendido = totales[9] or CERO
    facturas = [fila for fila in filas if fila[0] == "Factura"]
    ticket = (sum((fila[9] for fila in facturas), CERO) / len(facturas)) if facturas else CERO

    return Tabla(
        titulo="Libro de ventas",
        subtitulo=f"Comprobantes de venta autorizados · {filtro.etiqueta}",
        columnas=(
            Columna("Comprobante", ancho=1.3),
            Columna("Número", ancho=1.5),
            Columna("Fecha", "fecha", 0.8),
            Columna("Identificación", ancho=1.1),
            Columna("Razón social", ancho=2.2),
            Columna("Base 0 %", "dinero", 1.1),
            Columna("Base gravada", "dinero", 1.1),
            Columna("Base exenta", "dinero", 1.1),
            Columna("IVA", "dinero", 1.0),
            Columna("Total", "dinero", 1.2),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Total vendido", f"$ {totales[9]:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Comprobantes", str(len(filas))),
            ("Ticket promedio", f"$ {ticket:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Frente al período anterior", variacion(vendido, vendido_antes)),
        ),
        notas=(NOTA_VENTAS, "Las cifras incluyen el IVA en la columna «Total»."),
    )


def ventas_por_dia(filtro: Filtro) -> Tabla:
    """Cuánto se vendió cada día: la serie para mirar el movimiento del negocio."""
    por_dia: dict[date, dict[str, Any]] = defaultdict(
        lambda: {"comprobantes": 0, "base": CERO, "iva": CERO, "total": CERO}
    )
    for _clase, documento, signo, _campo in documentos_de_venta(filtro):
        datos = por_dia[documento.fecha_emision]
        bases = _bases(documento)
        datos["comprobantes"] += 1
        datos["base"] += (bases["base_0"] + bases["base_gravada"] + bases["base_exenta"]) * signo
        datos["iva"] += bases["iva"] * signo
        datos["total"] += _total(documento, signo)

    filas = [
        [dia, datos["comprobantes"], datos["base"], datos["iva"], datos["total"]]
        for dia, datos in sorted(por_dia.items())
    ]
    totales = [None, sumar(filas, 1), sumar(filas, 2), sumar(filas, 3), sumar(filas, 4)]
    mejor = max(por_dia.items(), key=lambda par: par[1]["total"], default=None)

    return Tabla(
        titulo="Ventas por día",
        subtitulo=f"Serie diaria de ventas · {filtro.etiqueta}",
        columnas=(
            Columna("Fecha", "fecha", 1.0),
            Columna("Comprobantes", "entero", 1.0),
            Columna("Base imponible", "dinero", 1.4),
            Columna("IVA", "dinero", 1.2),
            Columna("Total", "dinero", 1.4),
        ),
        filas=filas,
        totales=totales,
        grafico=tuple((fila[0].strftime("%d/%m"), fila[4]) for fila in filas),
        resumen=(
            ("Días con ventas", str(len(filas))),
            ("Promedio por día", f"$ {totales[4] / len(filas):,.2f}".replace(",", ".").replace(".", ",", 1) if filas else "—"),
            ("Mejor día", f"{mejor[0].strftime('%d/%m/%Y')} · $ {mejor[1]['total']:,.2f}".replace(",", ".").replace(".", ",", 1) if mejor else "—"),
        ),
        notas=(NOTA_VENTAS,),
    )


def ventas_clientes(filtro: Filtro) -> Tabla:
    """Quiénes compran y cuánto pesa cada uno: el ranking de clientes."""
    por_cliente: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"nombre": "", "comprobantes": 0, "base": CERO, "iva": CERO, "total": CERO}
    )
    for _clase, documento, signo, campo in documentos_de_venta(filtro):
        contraparte = _contraparte(documento, campo)
        identificacion = getattr(contraparte, "identificacion", "") or "s/n"
        datos = por_cliente[identificacion]
        datos["nombre"] = getattr(contraparte, "razon_social", "") or datos["nombre"]
        bases = _bases(documento)
        datos["comprobantes"] += 1
        datos["base"] += (bases["base_0"] + bases["base_gravada"] + bases["base_exenta"]) * signo
        datos["iva"] += bases["iva"] * signo
        datos["total"] += _total(documento, signo)

    ordenados = sorted(por_cliente.items(), key=lambda par: par[1]["total"], reverse=True)
    gran_total = sum((datos["total"] for _clave, datos in ordenados), CERO)
    filas = [
        [
            identificacion,
            datos["nombre"],
            datos["comprobantes"],
            datos["base"],
            datos["iva"],
            datos["total"],
            participacion(datos["total"], gran_total),
        ]
        for identificacion, datos in ordenados
    ]
    totales = [None, "Totales", sumar(filas, 2), sumar(filas, 3), sumar(filas, 4), sumar(filas, 5), participacion(gran_total, gran_total)]

    return Tabla(
        titulo="Ventas por cliente",
        subtitulo=f"Ranking de clientes · {filtro.etiqueta}",
        columnas=(
            Columna("Identificación", ancho=1.1),
            Columna("Cliente", ancho=2.6),
            Columna("Comprobantes", "entero", 0.9),
            Columna("Base imponible", "dinero", 1.3),
            Columna("IVA", "dinero", 1.0),
            Columna("Total", "dinero", 1.2),
            Columna("Participación", ancho=1.0),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Clientes", str(len(filas))),
            ("Total vendido", f"$ {gran_total:,.2f}".replace(",", ".").replace(".", ",", 1)),
            (
                "Primer cliente",
                f"{ordenados[0][1]['nombre']} · {participacion(ordenados[0][1]['total'], gran_total)}"
                if ordenados
                else "—",
            ),
        ),
        notas=(NOTA_VENTAS, "La participación es sobre el total vendido del período."),
    )


def ventas_por_usuario(filtro: Filtro) -> Tabla:
    """Quién vendió: los comprobantes y los importes de cada usuario del sistema.

    El usuario no viaja en el XML del SRI: lo anota el sistema al registrar el
    comprobante (``facturacion.auditoria``). Los comprobantes que no tengan esa
    anotación —de antes de que existiera, o hechos desde el admin— van en una fila
    aparte, para que la suma de los usuarios cuadre con el total vendido.
    """
    documentos = list(documentos_de_venta(filtro))
    usuarios = _registros_de_auditoria(documentos)

    por_usuario: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"comprobantes": 0, "base": CERO, "iva": CERO, "total": CERO}
    )
    for clase, documento, signo, _campo in documentos:
        nombre = usuarios.get((clase, documento.pk), "Sin usuario registrado")
        datos = por_usuario[nombre]
        bases = _bases(documento)
        datos["comprobantes"] += 1
        datos["base"] += (bases["base_0"] + bases["base_gravada"] + bases["base_exenta"]) * signo
        datos["iva"] += bases["iva"] * signo
        datos["total"] += _total(documento, signo)

    ordenados = sorted(por_usuario.items(), key=lambda par: par[1]["total"], reverse=True)
    gran_total = sum((datos["total"] for _nombre, datos in ordenados), CERO)
    filas = [
        [
            nombre,
            datos["comprobantes"],
            datos["base"],
            datos["iva"],
            datos["total"],
            participacion(datos["total"], gran_total),
        ]
        for nombre, datos in ordenados
    ]
    totales = [
        "Totales",
        sumar(filas, 1),
        sumar(filas, 2),
        sumar(filas, 3),
        sumar(filas, 4),
        participacion(gran_total, gran_total),
    ]

    return Tabla(
        titulo="Ventas por usuario",
        subtitulo=f"Quién registró cada comprobante · {filtro.etiqueta}",
        columnas=(
            Columna("Usuario", ancho=2.6),
            Columna("Comprobantes", "entero", 1.0),
            Columna("Base imponible", "dinero", 1.4),
            Columna("IVA", "dinero", 1.0),
            Columna("Total", "dinero", 1.3),
            Columna("Participación", ancho=1.0),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Usuarios que vendieron", str(sum(1 for fila in filas if fila[0] != "Sin usuario registrado"))),
            ("Total vendido", f"$ {gran_total:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            NOTA_VENTAS,
            "El usuario es el que registró el comprobante en el sistema: es un dato de "
            "control interno, no un dato que se envíe al SRI.",
        ),
    )


def _registros_de_auditoria(documentos: Sequence[tuple[str, Any, int, str]]) -> dict[tuple[str, int], str]:
    """El nombre del usuario de cada comprobante, en una sola consulta por tipo."""
    from facturacion.models import RegistroComprobante

    por_tipo: dict[str, list[int]] = defaultdict(list)
    for _clase, documento, _signo, _campo in documentos:
        tipo = str(getattr(documento, "TIPO_COMPROBANTE", "") or "")
        if tipo and documento.pk:
            por_tipo[tipo].append(documento.pk)

    registros: dict[tuple[str, int], str] = {}
    for tipo, identificadores in por_tipo.items():
        for registro in RegistroComprobante.objects.filter(
            tipo=tipo, objeto_id__in=identificadores
        ):
            registros[(tipo, registro.objeto_id)] = (
                registro.usuario_nombre
                or (registro.usuario.get_username() if registro.usuario_id else "")
                or "Sin usuario registrado"
            )
    return registros


def ventas_productos(filtro: Filtro) -> Tabla:
    """Qué se vende: bienes y servicios por cantidad, base y peso en la venta."""
    por_producto: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"descripcion": "", "cantidad": CERO, "base": CERO, "iva": CERO, "total": CERO}
    )
    for detalle, signo, _documento in _detalles_con_signo(filtro):
        clave = detalle.codigo_principal or detalle.descripcion
        datos = por_producto[clave]
        datos["descripcion"] = detalle.descripcion or datos["descripcion"]
        datos["cantidad"] += (detalle.cantidad or CERO) * signo
        datos["base"] += (detalle.precio_total_sin_impuesto or CERO) * signo
        datos["iva"] += (detalle.valor_iva or CERO) * signo
        datos["total"] += (detalle.total or CERO) * signo

    ordenados = sorted(por_producto.items(), key=lambda par: par[1]["total"], reverse=True)
    gran_total = sum((datos["total"] for _clave, datos in ordenados), CERO)
    filas = [
        [
            clave,
            datos["descripcion"],
            datos["cantidad"],
            datos["base"],
            datos["iva"],
            datos["total"],
            participacion(datos["total"], gran_total),
        ]
        for clave, datos in ordenados
    ]
    totales = [None, "Totales", sumar(filas, 2), sumar(filas, 3), sumar(filas, 4), sumar(filas, 5), participacion(gran_total, gran_total)]

    return Tabla(
        titulo="Ventas por producto y servicio",
        subtitulo=f"Detalle de lo vendido · {filtro.etiqueta}",
        columnas=(
            Columna("Código", ancho=1.0),
            Columna("Descripción", ancho=3.0),
            Columna("Cantidad", "numero", 0.9),
            Columna("Base imponible", "dinero", 1.3),
            Columna("IVA", "dinero", 1.0),
            Columna("Total", "dinero", 1.2),
            Columna("Participación", ancho=1.0),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Productos vendidos", str(len(filas))),
            ("Total vendido", f"$ {gran_total:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            NOTA_VENTAS,
            "Se suman las líneas de facturas, notas de crédito y liquidaciones de compra. "
            "Las notas de débito no llevan líneas y entran en el libro de ventas, no aquí.",
        ),
    )


def ventas_tarifas(filtro: Filtro) -> Tabla:
    """Las bases y el IVA por tarifa: lo que se traslada al formulario 104."""
    por_tarifa: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"base": CERO, "iva": CERO}
    )
    for detalle, signo, _documento in _detalles_con_signo(filtro):
        clave = str(detalle.codigo_porcentaje_iva or "")
        por_tarifa[clave]["base"] += (detalle.precio_total_sin_impuesto or CERO) * signo
        por_tarifa[clave]["iva"] += (detalle.valor_iva or CERO) * signo

    filas = [
        [_tarifa_de(clave), datos["base"], datos["iva"], datos["base"] + datos["iva"]]
        for clave, datos in sorted(por_tarifa.items())
    ]
    totales = [None, sumar(filas, 1), sumar(filas, 2), sumar(filas, 3)]

    return Tabla(
        titulo="Ventas por tarifa de IVA",
        subtitulo=f"Bases imponibles y IVA generado · {filtro.etiqueta}",
        columnas=(
            Columna("Tarifa", ancho=2.0),
            Columna("Base imponible", "dinero", 1.4),
            Columna("IVA", "dinero", 1.2),
            Columna("Base + IVA", "dinero", 1.4),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("IVA generado", f"$ {totales[2]:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Ventas gravadas", f"$ {totales[1]:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Las bases van sin impuesto y por tarifa, como se declaran en el formulario 104 "
            "de IVA (Servicio de Rentas Internas). Las tarifas vigentes las fija el SRI; "
            "el sistema usa las que tenga cargadas en cada producto.",
            NOTA_VENTAS,
        ),
    )


# ------------------------------------------------- comprobantes electrónicos


def _comprobantes_del_periodo(filtro: Filtro) -> Any:
    return _rango(ComprobanteEmitido.objects.all(), filtro).order_by(
        "fecha_emision", "estab", "pto_emi", "secuencial"
    )


def comprobantes(filtro: Filtro) -> Tabla:
    """El estado de cada comprobante ante el SRI, con su clave de acceso."""
    filas = []
    for comprobante in _comprobantes_del_periodo(filtro).select_related("configuracion"):
        filas.append(
            [
                TipoComprobante(comprobante.tipo_comprobante).label
                if comprobante.tipo_comprobante in TipoComprobante.values
                else comprobante.tipo_comprobante,
                comprobante.numero_comprobante,
                comprobante.fecha_emision,
                comprobante.identificacion_receptor,
                comprobante.razon_social_receptor,
                comprobante.importe_total,
                _etiqueta_estado(comprobante.estado),
                comprobante.numero_autorizacion or "—",
                comprobante.fecha_autorizacion,
            ]
        )
    totales = [None, None, None, None, "Total emitido", sumar(filas, 5), None, None, None]

    return Tabla(
        titulo="Comprobantes electrónicos emitidos",
        subtitulo=f"Estado ante el SRI · {filtro.etiqueta}",
        columnas=(
            Columna("Tipo", ancho=1.5),
            Columna("Número", ancho=1.5),
            Columna("Fecha", "fecha", 0.8),
            Columna("Identificación", ancho=1.1),
            Columna("Receptor", ancho=2.0),
            Columna("Importe", "dinero", 1.1),
            Columna("Estado", ancho=1.2),
            Columna("Autorización", ancho=1.6),
            Columna("Autorizado el", "fecha", 1.0),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Comprobantes", str(len(filas))),
            (
                "Autorizados",
                str(sum(1 for fila in filas if fila[6] == _etiqueta_estado(EstadoComprobante.AUTORIZADO.value))),
            ),
            ("Importe emitido", f"$ {totales[5]:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Se listan los comprobantes enviados al SRI en el período. La clave de acceso "
            "y el número de autorización son los que constan en el XML autorizado; el "
            "estado es el último que devolvió el Servicio de Rentas Internas.",
        ),
    )


def comprobantes_procesos(filtro: Filtro) -> Tabla:
    """Los procesos de emisión: cuántos van por tipo y estado y cuánto tardan."""
    por_tipo: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"cuantos": 0, "importe": CERO, "horas": []}
    )
    for comprobante in _comprobantes_del_periodo(filtro):
        tipo = (
            TipoComprobante(comprobante.tipo_comprobante).label
            if comprobante.tipo_comprobante in TipoComprobante.values
            else comprobante.tipo_comprobante
        )
        datos = por_tipo[(tipo, _etiqueta_estado(comprobante.estado))]
        datos["cuantos"] += 1
        datos["importe"] += comprobante.importe_total or CERO
        horas = _horas(comprobante.creado, comprobante.fecha_autorizacion)
        if horas is not None:
            datos["horas"].append(horas)

    filas = []
    for (tipo, estado), datos in sorted(por_tipo.items()):
        promedio = sum(datos["horas"]) / len(datos["horas"]) if datos["horas"] else None
        filas.append(
            [
                tipo,
                estado,
                datos["cuantos"],
                datos["importe"],
                promedio if promedio is not None else "—",
            ]
        )
    totales = [None, "Total", sumar(filas, 2), sumar(filas, 3), None]

    return Tabla(
        titulo="Procesos de emisión",
        subtitulo=f"Envíos al SRI por tipo y estado · {filtro.etiqueta}",
        columnas=(
            Columna("Comprobante", ancho=2.0),
            Columna("Estado", ancho=2.0),
            Columna("Cantidad", "entero", 1.0),
            Columna("Importe", "dinero", 1.4),
            Columna("Horas hasta autorizar", "numero", 1.2),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Comprobantes procesados", str(totales[2] or 0)),
            ("Sin autorizar", str(sum(fila[2] for fila in filas if fila[1] != _etiqueta_estado(EstadoComprobante.AUTORIZADO.value)))),
        ),
        notas=(
            "Las horas hasta autorizar se miden desde que se registró el comprobante hasta "
            "la fecha de autorización que devolvió el SRI.",
        ),
    )


def retenciones(filtro: Filtro) -> Tabla:
    """Las retenciones emitidas, con lo retenido por cada impuesto."""
    filas = []
    for retencion in (
        _rango(
            Retencion.objects.filter(comprobante__estado=EstadoComprobante.AUTORIZADO.value),
            filtro,
        )
        .select_related("sujeto_retenido", "comprobante")
        .prefetch_related("docs_sustento__retenciones", "docs_sustento__impuestos")
    ):
        base = CERO
        por_impuesto: dict[str, Decimal] = defaultdict(lambda: CERO)
        for sustento in retencion.docs_sustento.all():
            base += sustento.total_sin_impuestos or CERO
            for aplicada in sustento.retenciones.all():
                por_impuesto[str(aplicada.codigo)] += aplicada.valor_retenido or CERO
        total = sum(por_impuesto.values(), CERO)
        filas.append(
            [
                _numero(retencion),
                retencion.fecha_emision,
                getattr(retencion.sujeto_retenido, "identificacion", ""),
                getattr(retencion.sujeto_retenido, "razon_social", ""),
                base,
                por_impuesto.get("1", CERO),
                por_impuesto.get("2", CERO),
                por_impuesto.get("6", CERO),
                total,
            ]
        )
    totales = [None, None, None, "Total retenido", sumar(filas, 4), sumar(filas, 5), sumar(filas, 6), sumar(filas, 7), sumar(filas, 8)]

    return Tabla(
        titulo="Retenciones emitidas",
        subtitulo=f"Comprobantes de retención autorizados · {filtro.etiqueta}",
        columnas=(
            Columna("Número", ancho=1.6),
            Columna("Fecha", "fecha", 0.8),
            Columna("Identificación", ancho=1.1),
            Columna("Sujeto retenido", ancho=2.4),
            Columna("Base imponible", "dinero", 1.2),
            Columna("Renta", "dinero", 1.0),
            Columna("IVA", "dinero", 1.0),
            Columna("ISD", "dinero", 1.0),
            Columna("Total", "dinero", 1.1),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Retenciones", str(len(filas))),
            ("Renta retenida", f"$ {totales[5]:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("IVA retenido", f"$ {totales[6]:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Los valores son los que constan en cada comprobante de retención autorizado. "
            "Los códigos de retención y sus porcentajes son los de las tablas vigentes del "
            "SRI (renta, IVA e ISD).",
        ),
    )


# ------------------------------------------------------------- contabilidad


def libro_diario(filtro: Filtro) -> Tabla:
    """Todos los asientos contabilizados del período, línea por línea."""
    datos = informes.libro_diario(filtro.desde, filtro.hasta)
    filas = []
    for bloque in datos["filas"]:
        asiento = bloque["asiento"]
        for linea in bloque["lineas"]:
            filas.append(
                [
                    asiento.fecha,
                    asiento.numero or "—",
                    asiento.concepto,
                    f"{linea.cuenta.codigo} · {linea.cuenta.nombre}",
                    linea.descripcion,
                    linea.debe,
                    linea.haber,
                ]
            )
    totales = [None, None, None, None, "Totales", datos["total_debe"], datos["total_haber"]]

    return Tabla(
        titulo="Libro diario",
        subtitulo=f"Asientos contabilizados · {filtro.etiqueta}",
        columnas=(
            Columna("Fecha", "fecha", 0.8),
            Columna("Asiento", ancho=0.9),
            Columna("Concepto", ancho=2.4),
            Columna("Cuenta", ancho=2.4),
            Columna("Detalle", ancho=1.8),
            Columna("Debe", "dinero", 1.1),
            Columna("Haber", "dinero", 1.1),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Asientos", str(datos["cuantos"])),
            ("Total debe", f"$ {datos['total_debe']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Total haber", f"$ {datos['total_haber']:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Solo entran los asientos contabilizados: los borradores y los anulados quedan "
            "fuera, y el asiento de cierre no se mezcla con el movimiento del período.",
        ),
    )


def libro_mayor(filtro: Filtro, cuenta: Optional[Cuenta] = None) -> Tabla:
    """El extracto de una cuenta: saldo anterior, movimientos y saldo final."""
    if cuenta is None:
        cuenta = (
            Cuenta.objects.filter(lineas__isnull=False).order_by("codigo").first()
            or Cuenta.objects.order_by("codigo").first()
        )
    if cuenta is None:
        return Tabla(
            titulo="Libro mayor",
            subtitulo="Todavía no hay cuentas contables",
            columnas=(Columna("Cuenta"),),
            sin_datos="Cargue el plan de cuentas para poder ver el mayor.",
        )

    datos = informes.libro_mayor(cuenta, filtro.desde, filtro.hasta)
    filas = [
        [
            bloque["asiento"].fecha,
            bloque["asiento"].numero or "—",
            bloque["asiento"].concepto,
            bloque["linea"].descripcion,
            bloque["debe"],
            bloque["haber"],
            bloque["saldo"],
        ]
        for bloque in datos["filas"]
    ]
    totales = [None, None, None, "Totales", datos["total_debe"], datos["total_haber"], datos["saldo_final"]]

    return Tabla(
        titulo=f"Libro mayor · {cuenta.codigo} {cuenta.nombre}",
        subtitulo=f"Movimiento de la cuenta · {filtro.etiqueta}",
        columnas=(
            Columna("Fecha", "fecha", 0.8),
            Columna("Asiento", ancho=0.9),
            Columna("Concepto", ancho=2.6),
            Columna("Detalle", ancho=2.0),
            Columna("Debe", "dinero", 1.1),
            Columna("Haber", "dinero", 1.1),
            Columna("Saldo", "dinero", 1.2),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Saldo anterior", f"$ {datos['saldo_anterior']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Saldo final", f"$ {datos['saldo_final']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Movimientos", str(len(filas))),
        ),
        notas=("El saldo anterior es el de la cuenta hasta el día antes del período.",),
    )


def balance(filtro: Filtro) -> Tabla:
    """Sumas y saldos por cuenta: el balance de comprobación."""
    datos = informes.balance_comprobacion(filtro.desde, filtro.hasta)
    filas = [
        [fila["codigo"], fila["nombre"], fila["debe"], fila["haber"], fila["saldo_deudor"], fila["saldo_acreedor"]]
        for fila in datos["filas"]
    ]
    totales = ["", "Totales", datos["total_debe"], datos["total_haber"], datos["total_debe"], datos["total_haber"]]

    return Tabla(
        titulo="Balance de comprobación",
        subtitulo=f"Sumas y saldos · {filtro.etiqueta}",
        columnas=(
            Columna("Código", ancho=1.0),
            Columna("Cuenta", ancho=3.2),
            Columna("Debe", "dinero", 1.2),
            Columna("Haber", "dinero", 1.2),
            Columna("Saldo deudor", "dinero", 1.2),
            Columna("Saldo acreedor", "dinero", 1.2),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Cuentas con movimiento", str(len(filas))),
            ("Suma del debe", f"$ {datos['total_debe']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Suma del haber", f"$ {datos['total_haber']:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Las cuentas madre muestran lo suyo más lo de sus hijas; los totales suman solo "
            "las cuentas de último nivel para no contar dos veces.",
        ),
    )


def resultados(filtro: Filtro) -> Tabla:
    """Ingresos, costos y gastos del período, con la utilidad del ejercicio."""
    datos = informes.estado_resultados(filtro.desde, filtro.hasta)
    filas = []
    for grupo, clave in (("Ingreso", "ingresos"), ("Costo", "costos"), ("Gasto", "gastos")):
        for fila in datos[clave]:
            filas.append([grupo, fila["codigo"], fila["nombre"], fila["valor"]])
    totales = [None, None, "Resultado del período", datos["resultado"]]

    return Tabla(
        titulo="Estado de resultados",
        subtitulo=f"Ingresos, costos y gastos · {filtro.etiqueta}",
        columnas=(
            Columna("Grupo", ancho=1.1),
            Columna("Código", ancho=1.0),
            Columna("Cuenta", ancho=4.0),
            Columna("Valor", "dinero", 1.6),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Ingresos", f"$ {datos['total_ingresos']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Costos", f"$ {datos['total_costos']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Gastos", f"$ {datos['total_gastos']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Utilidad del período", f"$ {datos['resultado']:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Se prepara por el principio de devengo: los ingresos y los gastos van al período "
            "en que se causan, no al que se cobran o se pagan. Los ingresos se presentan "
            "netos de notas de crédito.",
        ),
    )


def situacion(filtro: Filtro) -> Tabla:
    """Activo, pasivo y patrimonio al cierre del período."""
    datos = informes.estado_situacion(filtro.hasta)
    filas = []
    for grupo, clave in (("Activo", "activo"), ("Pasivo", "pasivo"), ("Patrimonio", "patrimonio")):
        for fila in datos[clave]:
            filas.append([grupo, fila["codigo"], fila["nombre"], fila["valor"]])
    totales = [None, None, "Pasivo + patrimonio", datos["total_pasivo_patrimonio"]]

    return Tabla(
        titulo="Estado de situación financiera",
        subtitulo=f"Al {filtro.hasta.strftime('%d/%m/%Y')}",
        columnas=(
            Columna("Grupo", ancho=1.1),
            Columna("Código", ancho=1.0),
            Columna("Cuenta", ancho=4.0),
            Columna("Valor", "dinero", 1.6),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Total activo", f"$ {datos['total_activo']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Total pasivo", f"$ {datos['total_pasivo']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Total patrimonio", f"$ {datos['total_patrimonio']:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Diferencia", f"$ {datos['diferencia']:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "El patrimonio incluye el resultado del ejercicio que todavía no se ha cerrado. "
            "La diferencia tiene que ser cero: si no lo es, hay un asiento descuadrado.",
        ),
    )


# ------------------------------------------------------ compras e inventario


def compras(filtro: Filtro) -> Tabla:
    """El registro de compras del período, con sus bases y su IVA."""
    filas = []
    for compra in _rango(
        Compra.objects.select_related("proveedor", "retencion"), filtro, campo="fecha"
    ).order_by("fecha", "pk"):
        filas.append(
            [
                compra.numero_con_guiones,
                compra.fecha,
                compra.proveedor.identificacion,
                compra.proveedor.razon_social,
                compra.base_iva_0,
                compra.base_iva,
                compra.base_no_grava + compra.base_exenta,
                compra.valor_iva,
                compra.total,
                compra.get_tipo_comprobante_display(),
            ]
        )
    totales = [None, None, None, "Totales"] + [sumar(filas, posicion) for posicion in range(4, 9)] + [None]

    return Tabla(
        titulo="Registro de compras",
        subtitulo=f"Compras y gastos con comprobante · {filtro.etiqueta}",
        columnas=(
            Columna("Número", ancho=1.5),
            Columna("Fecha", "fecha", 0.8),
            Columna("Identificación", ancho=1.1),
            Columna("Proveedor", ancho=2.4),
            Columna("Base 0 %", "dinero", 1.0),
            Columna("Base IVA", "dinero", 1.0),
            Columna("No grava / exenta", "dinero", 1.1),
            Columna("IVA", "dinero", 1.0),
            Columna("Total", "dinero", 1.1),
            Columna("Comprobante", ancho=1.4),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Compras", str(len(filas))),
            ("Total comprado", f"$ {totales[8]:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("IVA en compras", f"$ {totales[7]:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Solo el sustento «01» (factura) genera crédito tributario de IVA. Las compras "
            "se registran con el comprobante del proveedor y su autorización, que es lo que "
            "pide el anexo ATS.",
        ),
    )


def inventario_movimientos(filtro: Filtro) -> Tabla:
    """Entradas, salidas y ajustes de existencias del período."""
    filas = []
    for movimiento in _rango(
        Movimiento.objects.select_related("producto", "usuario"), filtro, campo="fecha"
    ).order_by("fecha", "pk"):
        filas.append(
            [
                movimiento.fecha,
                movimiento.producto.codigo_principal if movimiento.producto else "",
                movimiento.producto.descripcion if movimiento.producto else "",
                movimiento.get_tipo_display(),
                movimiento.cantidad,
                movimiento.motivo,
                movimiento.usuario.get_username() if movimiento.usuario else "—",
            ]
        )
    entradas = sum(
        (fila[4] for fila in filas if fila[3] == TipoMovimiento.ENTRADA.label), CERO
    )
    salidas = sum((fila[4] for fila in filas if fila[3] == TipoMovimiento.SALIDA.label), CERO)

    return Tabla(
        titulo="Movimientos de inventario",
        subtitulo=f"Entradas, salidas y ajustes · {filtro.etiqueta}",
        columnas=(
            Columna("Fecha", "fecha", 0.8),
            Columna("Código", ancho=1.0),
            Columna("Producto", ancho=3.0),
            Columna("Tipo", ancho=1.4),
            Columna("Cantidad", "numero", 1.0),
            Columna("Motivo", ancho=2.0),
            Columna("Usuario", ancho=1.2),
        ),
        filas=filas,
        resumen=(
            ("Movimientos", str(len(filas))),
            ("Entradas", f"{entradas:,.2f}".replace(",", ".").replace(".", ",", 1)),
            ("Salidas", f"{salidas:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "Las salidas por factura las genera la emisión del comprobante; las demás se "
            "registran a mano en el kardex de cada producto.",
        ),
    )


def inventario_existencias(_filtro: Filtro) -> Tabla:
    """Lo que hay en bodega hoy, con su costo y su aviso de reposición."""
    from inventario.models import Existencia

    filas = []
    for existencia in Existencia.objects.select_related("producto").order_by("producto__descripcion"):
        producto = existencia.producto
        filas.append(
            [
                producto.codigo_principal,
                producto.descripcion,
                existencia.cantidad,
                existencia.minimo,
                producto.precio_unitario,
                existencia.valor,
                "Sí" if existencia.bajo_minimo else "No",
            ]
        )
    valor = sumar(filas, 5)
    totales = [None, "Valor del inventario", None, None, None, valor, None]

    return Tabla(
        titulo="Existencias en bodega",
        subtitulo="Al día de hoy",
        columnas=(
            Columna("Código", ancho=1.0),
            Columna("Producto", ancho=3.4),
            Columna("Cantidad", "numero", 1.0),
            Columna("Mínimo", "numero", 0.9),
            Columna("Precio unitario", "dinero", 1.1),
            Columna("Valor", "dinero", 1.2),
            Columna("Bajo el mínimo", ancho=1.0),
        ),
        filas=filas,
        totales=totales,
        resumen=(
            ("Productos", str(len(filas))),
            ("Bajo el mínimo", str(sum(1 for fila in filas if fila[6] == "Sí"))),
            ("Valor del inventario", f"$ {valor:,.2f}".replace(",", ".").replace(".", ",", 1)),
        ),
        notas=(
            "El valor sale de la cantidad por el costo del producto. Es una foto del "
            "momento en que se pide el reporte, no del período elegido.",
        ),
    )
