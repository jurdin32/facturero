"""El catálogo de reportes: qué se puede sacar y en qué apartado va.

Cada reporte es una entrada con su nombre, su explicación y la función que arma la
tabla. La pantalla, el PDF y el Excel salen de aquí, así que añadir un reporte es
añadir una entrada y su consulta: no hay que tocar ni las plantillas ni las vistas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from . import consultas
from .periodos import Filtro
from .tabla import Tabla

__all__ = ["GRUPOS", "POR_CLAVE", "REPORTES", "Reporte", "de", "por_grupo"]


@dataclass(frozen=True, slots=True)
class Reporte:
    """Un reporte del catálogo."""

    clave: str
    nombre: str
    grupo: str
    descripcion: str
    construir: Callable[..., Tabla]
    icono: str = "charts"
    #: La norma o el trámite con el que se relaciona. Va en la tarjeta y al pie.
    base: str = ""
    #: Si necesita elegir una cuenta (el libro mayor, por ejemplo).
    pide_cuenta: bool = False


#: Los apartados, en el orden en que se enseñan.
GRUPOS: tuple[str, ...] = (
    "Ventas y facturación",
    "Comprobantes electrónicos",
    "Compras",
    "Contabilidad",
    "Inventario",
)

REPORTES: tuple[Reporte, ...] = (
    # ---------------------------------------------------------------- ventas
    Reporte(
        clave="ventas",
        nombre="Libro de ventas",
        grupo="Ventas y facturación",
        descripcion=(
            "Cada comprobante autorizado del período con sus bases por tarifa, su IVA y "
            "su total. Es el registro que respalda la declaración de IVA."
        ),
        construir=consultas.ventas,
        icono="receipt",
        base="Reglamento de Comprobantes de Venta, Retención y Documentos Complementarios.",
    ),
    Reporte(
        clave="ventas_por_dia",
        nombre="Ventas por día",
        grupo="Ventas y facturación",
        descripcion=(
            "La serie diaria de ventas con el promedio del período y el mejor día: sirve "
            "para ver el movimiento del negocio y compararlo con otros períodos."
        ),
        construir=consultas.ventas_por_dia,
        icono="bar-chart",
    ),
    Reporte(
        clave="ventas_clientes",
        nombre="Ventas por cliente",
        grupo="Ventas y facturación",
        descripcion=(
            "El ranking de clientes por monto, con su participación sobre el total vendido."
        ),
        construir=consultas.ventas_clientes,
        icono="account-circle",
    ),
    Reporte(
        clave="ventas_productos",
        nombre="Ventas por producto y servicio",
        grupo="Ventas y facturación",
        descripcion=(
            "Qué se vendió, en qué cantidad y cuánto pesa cada bien o servicio en la venta "
            "del período."
        ),
        construir=consultas.ventas_productos,
        icono="cart-product",
    ),
    Reporte(
        clave="ventas_por_usuario",
        nombre="Ventas por usuario",
        grupo="Ventas y facturación",
        descripcion=(
            "Quién registró cada comprobante y cuánto vendió: sirve para el control interno "
            "del equipo y para liquidar comisiones por vendedor."
        ),
        construir=consultas.ventas_por_usuario,
        icono="account-circle",
        base="Control interno: el usuario no es un dato del comprobante electrónico.",
    ),
    Reporte(
        clave="ventas_tarifas",
        nombre="Ventas por tarifa de IVA",
        grupo="Ventas y facturación",
        descripcion=(
            "Las bases imponibles separadas por tarifa (0 %, 5 %, 15 %, no objeto y exento) "
            "y el IVA generado: el resumen que se traslada al formulario 104."
        ),
        construir=consultas.ventas_tarifas,
        icono="money",
        base="Formulario 104 de IVA (Servicio de Rentas Internas).",
    ),
    # ----------------------------------------------------------- comprobantes
    Reporte(
        clave="comprobantes",
        nombre="Comprobantes emitidos",
        grupo="Comprobantes electrónicos",
        descripcion=(
            "Todos los comprobantes enviados al SRI en el período, con su clave de acceso, "
            "su número de autorización y el estado en que quedaron."
        ),
        construir=consultas.comprobantes,
        icono="description",
        base="Comprobantes electrónicos y su autorización (Servicio de Rentas Internas).",
    ),
    Reporte(
        clave="comprobantes_procesos",
        nombre="Procesos de emisión",
        grupo="Comprobantes electrónicos",
        descripcion=(
            "Cuántos comprobantes van por tipo y estado y cuánto tardó el SRI en autorizar: "
            "el control del proceso de emisión."
        ),
        construir=consultas.comprobantes_procesos,
        icono="charts",
    ),
    Reporte(
        clave="retenciones",
        nombre="Retenciones emitidas",
        grupo="Comprobantes electrónicos",
        descripcion=(
            "Los comprobantes de retención autorizados, con lo retenido por renta, IVA e ISD "
            "y su base imponible."
        ),
        construir=consultas.retenciones,
        icono="money",
        base="Comprobantes de retención y tablas de porcentajes del SRI.",
    ),
    # --------------------------------------------------------------- compras
    Reporte(
        clave="compras",
        nombre="Registro de compras",
        grupo="Compras",
        descripcion=(
            "Las compras y gastos con comprobante del período, con sus bases, su IVA y el "
            "sustento tributario."
        ),
        construir=consultas.compras,
        icono="cart-product",
        base="Anexo ATS y formulario 104 (Servicio de Rentas Internas).",
    ),
    # ---------------------------------------------------------- contabilidad
    Reporte(
        clave="libro_diario",
        nombre="Libro diario",
        grupo="Contabilidad",
        descripcion="Todos los asientos contabilizados del período, línea por línea.",
        construir=consultas.libro_diario,
        icono="books",
        base="Normas Internacionales de Información Financiera (NIIF) para pymes.",
    ),
    Reporte(
        clave="libro_mayor",
        nombre="Libro mayor",
        grupo="Contabilidad",
        descripcion=(
            "El extracto de una cuenta: saldo anterior, movimientos del período y saldo final."
        ),
        construir=consultas.libro_mayor,
        icono="library",
        pide_cuenta=True,
    ),
    Reporte(
        clave="balance",
        nombre="Balance de comprobación",
        grupo="Contabilidad",
        descripcion="Sumas y saldos por cuenta, con las cuentas madre sumando a sus hijas.",
        construir=consultas.balance,
        icono="balance",
        base="Normas Internacionales de Información Financiera (NIIF) para pymes.",
    ),
    Reporte(
        clave="resultados",
        nombre="Estado de resultados",
        grupo="Contabilidad",
        descripcion=(
            "Ingresos, costos y gastos del período con la utilidad resultante, preparado por "
            "el principio de devengo."
        ),
        construir=consultas.resultados,
        icono="calculate",
        base="NIIF para pymes, sección 5 (estado del resultado integral).",
    ),
    Reporte(
        clave="situacion",
        nombre="Estado de situación financiera",
        grupo="Contabilidad",
        descripcion=(
            "Activo, pasivo y patrimonio al cierre de la fecha pedida, con el resultado del "
            "ejercicio incluido."
        ),
        construir=consultas.situacion,
        icono="bank",
        base="NIIF para pymes, sección 4 (estado de situación financiera).",
    ),
    # ---------------------------------------------------------- inventario
    Reporte(
        clave="inventario_movimientos",
        nombre="Movimientos de inventario",
        grupo="Inventario",
        descripcion=(
            "Las entradas, salidas y ajustes del período, con su motivo y el usuario que los "
            "registró."
        ),
        construir=consultas.inventario_movimientos,
        icono="database",
    ),
    Reporte(
        clave="inventario_existencias",
        nombre="Existencias en bodega",
        grupo="Inventario",
        descripcion=(
            "Lo que hay de cada producto al día de hoy, con su valor y el aviso de los que "
            "están bajo el mínimo."
        ),
        construir=consultas.inventario_existencias,
        icono="cube",
    ),
)

#: Los reportes por su clave, para resolver la dirección.
POR_CLAVE: dict[str, Reporte] = {reporte.clave: reporte for reporte in REPORTES}


def de(clave: str) -> Optional[Reporte]:
    """El reporte de esa clave, o ``None`` si no existe."""
    return POR_CLAVE.get(clave)


def por_grupo() -> list[tuple[str, list[Reporte]]]:
    """Los reportes agrupados por apartado, en el orden del catálogo."""
    return [
        (grupo, [reporte for reporte in REPORTES if reporte.grupo == grupo])
        for grupo in GRUPOS
    ]


def construir(reporte: Reporte, filtro: Filtro, **extra) -> Tabla:
    """Arma la tabla del reporte con el filtro pedido."""
    if reporte.pide_cuenta:
        return reporte.construir(filtro, cuenta=extra.get("cuenta"))
    return reporte.construir(filtro)
