"""Las cuentas del tablero: qué se ha facturado y qué pide atención.

Los importes salen de ``Factura.total``, que es una cuenta de Python (la suma de
las líneas), así que se suman en memoria. Para el tamaño de una tienda es de sobra
y evita tener dos verdades sobre lo que vale una factura.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from factec.django.documentos import Factura, FacturaDetalle
from factec.django.models import EstadoComprobante

from inventario.models import Existencia

#: Días que se pueden mirar en el gráfico.
PERIODOS = (7, 14, 30, 90)


def _suma(facturas: Any) -> Decimal:
    return sum((f.total for f in facturas), Decimal("0"))


def hoy_y_ayer() -> tuple[date, date]:
    from factec.sri.fechas import hoy_en_ecuador

    hoy = hoy_en_ecuador()
    return hoy, hoy - timedelta(days=1)


def contadores(hoy: date) -> dict[str, Any]:
    """Los cuatro números de arriba: hoy, el mes, autorizadas y por resolver."""
    desde_mes = hoy.replace(day=1)

    de_hoy = list(
        Factura.objects.filter(fecha_emision=hoy)
        .select_related("comprobante")
        .prefetch_related("detalles")
    )
    del_mes = list(
        Factura.objects.filter(fecha_emision__gte=desde_mes, fecha_emision__lte=hoy)
        .select_related("comprobante")
        .prefetch_related("detalles")
    )
    autorizadas = Factura.objects.filter(comprobante__estado=EstadoComprobante.AUTORIZADO)
    por_resolver = Factura.objects.filter(
        Q(comprobante__isnull=True)
        | Q(
            comprobante__estado__in=[
                EstadoComprobante.DEVUELTO,
                EstadoComprobante.NO_AUTORIZADO,
                EstadoComprobante.ERROR,
                EstadoComprobante.EN_PROCESO,
                EstadoComprobante.FIRMADO,
                EstadoComprobante.RECIBIDO,
                EstadoComprobante.BORRADOR,
            ]
        )
    )
    cuantas_autorizadas = autorizadas.count()
    emitidas = Factura.objects.exclude(comprobante__isnull=True).count()

    return {
        "hoy": {"importe": _suma(de_hoy), "cuantas": len(de_hoy)},
        "mes": {"importe": _suma(del_mes), "cuantas": len(del_mes), "desde": desde_mes},
        "autorizadas": {
            "cuantas": cuantas_autorizadas,
            "emitidas": emitidas,
            "porcentaje": round(cuantas_autorizadas / emitidas * 100) if emitidas else 0,
        },
        "por_resolver": {
            "cuantas": por_resolver.count(),
            "en_marcha": por_resolver.filter(
                comprobante__estado__in=[
                    EstadoComprobante.FIRMADO,
                    EstadoComprobante.RECIBIDO,
                    EstadoComprobante.EN_PROCESO,
                ]
            ).count(),
        },
    }


def ventas_por_dia(hoy: date, dias: int) -> dict[str, Any]:
    """El importe autorizado de cada día del periodo, para el gráfico de barras."""
    desde = hoy - timedelta(days=dias - 1)
    facturas = (
        Factura.objects.filter(fecha_emision__gte=desde, fecha_emision__lte=hoy)
        .select_related("comprobante")
        .prefetch_related("detalles")
    )

    por_dia: dict[date, Decimal] = {desde + timedelta(days=i): Decimal("0") for i in range(dias)}
    for factura in facturas:
        por_dia[factura.fecha_emision] = por_dia.get(factura.fecha_emision, Decimal("0")) + factura.total

    alto = max(por_dia.values()) if por_dia else Decimal("0")
    # Con muchas barras, la fecha se pone de vez en cuando: si no, se pisan.
    cada = 1 if dias <= 7 else 3
    ordenados = sorted(por_dia.items())
    barras = [
        {
            "fecha": dia,
            "importe": importe,
            "alto": round(float(importe / alto) * 100, 2) if alto else 0,
            "etiqueta": dia.strftime("%d/%m"),
            "marcar": posicion % cada == 0 or posicion == len(ordenados) - 1,
        }
        for posicion, (dia, importe) in enumerate(ordenados)
    ]
    return {
        "barras": barras,
        "total": sum(por_dia.values(), Decimal("0")),
        "alto": alto,
        "desde": desde,
        "dias": dias,
    }


#: Cómo se puede ordenar el gráfico de lo que más se mueve. La clave es la
#: anotación de la consulta y el nombre, lo que se lee en el botón.
ORDENES = (
    ("unidades", "Unidades"),
    ("veces", "Veces"),
    ("importe", "Importe"),
)

#: Qué se mira de serie: el movimiento son las unidades que salen.
ORDEN_POR_OMISION = "unidades"


def mas_movidos(
    hoy: date, dias: int, orden: str = ORDEN_POR_OMISION, limite: int = 8
) -> dict[str, Any]:
    """Los productos y servicios que más se mueven en el periodo, para el gráfico.

    Se cuenta por la **descripción** de la línea, que es lo que llevan todas (el
    producto del catálogo puede faltar: hay líneas escritas a mano). De cada uno se
    sacan las tres cuentas —unidades, veces que se factura e importe— y se ordena
    por la que se pida; la barra del gráfico va con la más alta.
    """
    desde = hoy - timedelta(days=dias - 1)
    anotacion = {"unidades": "piezas", "veces": "veces", "importe": "importe"}
    renglon = ExpressionWrapper(
        F("cantidad") * F("precio_unitario"),
        output_field=DecimalField(max_digits=16, decimal_places=6),
    )
    filas = list(
        FacturaDetalle.objects.filter(
            factura__fecha_emision__gte=desde, factura__fecha_emision__lte=hoy
        )
        .values("descripcion")
        .annotate(
            veces=Count("id"),
            # Ojo: no llamar «cantidad» a esta cuenta, o el Sum de abajo se
            # encontraría a sí mismo al resolver F("cantidad").
            piezas=Coalesce(
                Sum("cantidad"), Decimal("0"),
                output_field=DecimalField(max_digits=16, decimal_places=6),
            ),
            importe=Coalesce(
                Sum(renglon), Decimal("0"),
                output_field=DecimalField(max_digits=16, decimal_places=6),
            ),
        )
        .order_by(f"-{anotacion[orden]}", "-importe", "descripcion")[:limite]
    )

    clave = anotacion[orden]
    mayor = max((fila[clave] for fila in filas), default=Decimal("0"))
    return {
        "filas": [
            {
                "descripcion": (fila["descripcion"] or "").strip() or "(sin descripción)",
                "veces": fila["veces"],
                "piezas": fila["piezas"],
                "importe": fila["importe"],
                "valor": fila[clave],
                "alto": round(float(fila[clave] / mayor) * 100, 2) if mayor else 0,
            }
            for fila in filas
        ],
        "unidades": sum((fila["piezas"] for fila in filas), Decimal("0")),
        "importe": sum((fila["importe"] for fila in filas), Decimal("0")),
        "unidad": dict(ORDENES)[orden],
        "orden": orden,
        "desde": desde,
        "dias": dias,
    }


def bajo_minimo(limite: int = 5) -> list[Existencia]:
    """Existencias por debajo de su mínimo (o en cero)."""
    from factec.django.documentos import TipoProducto

    existencias = list(
        Existencia.objects.select_related("producto")
        .filter(producto__tipo=TipoProducto.PRODUCTO.value)
        .order_by("cantidad")
    )
    return [existencia for existencia in existencias if existencia.bajo_minimo][:limite]
