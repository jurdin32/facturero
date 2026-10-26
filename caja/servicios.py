"""Reglas de la caja: una abierta por usuario y movimientos con importe positivo."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CERO, MovimientoCaja, SesionCaja

__all__ = [
    "BILLETES",
    "REVISIONES",
    "anular_vale",
    "cobrar_vale",
    "crear_vale",
    "revisar",
    "DENOMINACIONES",
    "MONEDAS",
    "abrir",
    "cerrar",
    "registrar_ingreso_factura",
    "registrar_movimiento",
    "sesion_abierta",
    "total_del_desglose",
]

#: Los billetes y monedas de dólar que circulan en el Ecuador, de mayor a menor. El
#: cierre se cuenta con esto: no hay moneda de 1 dólar en billete propio desde el
#: año 2000, pero sí la moneda, y por eso va en las dos listas.
BILLETES = (
    Decimal("100"),
    Decimal("50"),
    Decimal("20"),
    Decimal("10"),
    Decimal("5"),
    Decimal("2"),
    Decimal("1"),
)

MONEDAS = (
    Decimal("0.50"),
    Decimal("0.25"),
    Decimal("0.10"),
    Decimal("0.05"),
    Decimal("0.01"),
)

#: Todas las denominaciones, en el orden en que se cuenta la caja.
DENOMINACIONES = BILLETES + MONEDAS


def total_del_desglose(desglose: dict[str, Any]) -> Decimal:
    """Cuánto dinero suman los billetes y monedas contados."""
    total = CERO
    for clave, cantidad in (desglose or {}).items():
        try:
            total += Decimal(str(clave)) * int(cantidad or 0)
        except (ArithmeticError, ValueError, TypeError):
            continue
    return total


def sesion_abierta(usuario: Any) -> Optional[SesionCaja]:
    return SesionCaja.objects.filter(
        usuario=usuario, estado=SesionCaja.Estado.ABIERTA.value
    ).first()


def abrir(usuario: Any, saldo_inicial: Decimal = CERO, observaciones: str = "") -> SesionCaja:
    if sesion_abierta(usuario) is not None:
        raise ValidationError("Ya tiene una caja abierta: ciérrela antes de abrir otra.")
    sesion = SesionCaja(
        usuario=usuario,
        saldo_inicial=saldo_inicial or CERO,
        observaciones=observaciones,
    )
    sesion.full_clean()
    with transaction.atomic():
        sesion.save()
    return sesion


def registrar_movimiento(
    sesion: SesionCaja,
    usuario: Any,
    *,
    tipo: str,
    concepto: str,
    importe: Decimal,
    referencia: str = "",
    comprobante: Any = None,
) -> MovimientoCaja:
    if not sesion.abierta:
        raise ValidationError("La caja está cerrada: no admite movimientos.")
    if tipo not in {MovimientoCaja.Tipo.INGRESO.value, MovimientoCaja.Tipo.EGRESO.value}:
        raise ValidationError("El movimiento debe ser un ingreso o un egreso.")
    if importe is None or importe <= CERO:
        raise ValidationError("El importe debe ser mayor que cero.")
    movimiento = MovimientoCaja(
        sesion=sesion,
        tipo=tipo,
        concepto=concepto.strip(),
        referencia=(referencia or "").strip(),
        importe=importe,
        usuario=usuario,
        comprobante=comprobante,
    )
    movimiento.full_clean()
    movimiento.save()
    return movimiento


def cerrar(
    sesion: SesionCaja,
    saldo_declarado: Decimal,
    observaciones: str = "",
    desglose: Optional[dict[str, Any]] = None,
) -> SesionCaja:
    with transaction.atomic():
        cerrada = SesionCaja.objects.select_for_update().get(pk=sesion.pk)
        cerrada.cerrar(saldo_declarado, observaciones, desglose)
    # El objeto que tenía la vista también queda cerrado: así no se le puede
    # seguir añadiendo un movimiento por descuido.
    for campo in (
        "estado",
        "cerrada_en",
        "saldo_declarado",
        "observaciones_cierre",
        "desglose",
        "actualizado",
    ):
        setattr(sesion, campo, getattr(cerrada, campo))
    return cerrada


def registrar_ingreso_factura(factura: Any, usuario: Any) -> Optional[MovimientoCaja]:
    """Si la factura se cobró en efectivo, la suma a la caja abierta del usuario.

    No bloquea la emisión: si no hay caja abierta se ignora. El comprobante evita
    que un reintento del SRI cuente dos veces el mismo cobro.
    """
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return None
    if str(getattr(factura, "forma_pago", "")) != "01":
        return None
    sesion = sesion_abierta(usuario)
    if sesion is None:
        return None
    comprobante = getattr(factura, "comprobante", None)
    if comprobante is not None and MovimientoCaja.objects.filter(
        sesion=sesion,
        comprobante=comprobante,
        tipo=MovimientoCaja.Tipo.INGRESO.value,
    ).exists():
        return None
    numero = ""
    if comprobante is not None:
        numero = f"{comprobante.estab}-{comprobante.pto_emi}-{comprobante.secuencial}"
    concepto = f"Cobro de factura {numero}".strip()
    referencia = getattr(getattr(factura, "receptor", None), "razon_social", "") or ""
    return registrar_movimiento(
        sesion,
        usuario,
        tipo=MovimientoCaja.Tipo.INGRESO.value,
        concepto=concepto,
        importe=factura.total,
        referencia=referencia,
        comprobante=comprobante,
    )


#: Lo que puede decir la revisión de un cuadre, con su nombre para la pantalla.
REVISIONES = (
    ("aprobada", "Aprobar el cuadre"),
    ("observada", "Dejarlo observado"),
)


def revisar(sesion: SesionCaja, revisor: Any, decision: str, nota: str = "") -> SesionCaja:
    """Aprobar el cuadre de un turno o dejarlo observado, con su nota.

    No se revisa una caja abierta: primero se cierra. Y el que revisa queda
    anotado, que es lo que se busca cuando alguien pregunta quién dio el visto
    bueno.
    """
    if decision not in dict(REVISIONES):
        raise ValidationError("Esa revisión no existe.")
    if sesion.abierta:
        raise ValidationError("Primero se cierra la caja; después se revisa el cuadre.")
    sesion.revision = decision
    sesion.revisada_por = revisor if getattr(revisor, "is_authenticated", False) else None
    sesion.revisada_en = timezone.now()
    sesion.nota_revision = (nota or "").strip()
    sesion.save(update_fields=["revision", "revisada_por", "revisada_en", "nota_revision", "actualizado"])
    return sesion


def crear_vale(
    *,
    responsable: Any,
    importe: Decimal,
    motivo: str,
    tipo: str = "faltante",
    sesion: Any = None,
    creado_por: Any = None,
    nota: str = "",
    fecha: Any = None,
) -> Any:
    """Un vale de caja: el faltante que se le cobra a alguien o el efectivo que saca.

    Nace **pendiente**. Si viene de una caja con faltante, el importe no puede pasar
    de lo que falta: el vale cubre el saldo en contra, no lo inventa.
    """
    from .models import ValeCaja

    if tipo not in ValeCaja.Tipo.values:
        raise ValidationError("Ese tipo de vale no existe.")
    if sesion is not None:
        if sesion.abierta:
            raise ValidationError("El vale se hace sobre una caja cerrada.")
        if tipo == ValeCaja.Tipo.FALTANTE.value:
            falta = -sesion.diferencia if sesion.diferencia < CERO else CERO
            if falta <= CERO:
                raise ValidationError("Esta caja no tiene faltante: no hay saldo que cobrar.")
            ya_cubierto = sum(
                vale.importe
                for vale in sesion.vales.exclude(estado=ValeCaja.Estado.ANULADO.value)
            )
            if ya_cubierto + importe > falta:
                disponible = (falta - ya_cubierto).quantize(Decimal("0.01"))
                raise ValidationError(
                    f"El faltante de esta caja es {falta:.2f} y ya hay vales por "
                    f"{ya_cubierto:.2f}: quedan {disponible:.2f}."
                )

    vale = ValeCaja(
        sesion=sesion,
        responsable=responsable,
        tipo=tipo,
        motivo=(motivo or "").strip(),
        importe=importe,
        creado_por=creado_por if getattr(creado_por, "is_authenticated", False) else None,
        nota=(nota or "").strip(),
        fecha=fecha or timezone.localdate(),
    )
    vale.full_clean()
    with transaction.atomic():
        vale.save()
    return vale


def cobrar_vale(vale: Any, nota: str = "") -> Any:
    """Dar por cobrado el vale (o por repuesto, si era un gasto)."""
    from .models import ValeCaja

    if vale.estado != ValeCaja.Estado.PENDIENTE.value:
        raise ValidationError("Ese vale ya no está pendiente.")
    vale.estado = ValeCaja.Estado.COBRADO.value
    vale.cobrado_en = timezone.localdate()
    if nota:
        vale.nota = (vale.nota + "\n" + nota).strip()
    vale.save()
    return vale


def anular_vale(vale: Any, nota: str = "") -> Any:
    """Anular un vale que no tenía por qué existir."""
    from .models import ValeCaja

    if vale.estado == ValeCaja.Estado.ANULADO.value:
        raise ValidationError("Ese vale ya está anulado.")
    vale.estado = ValeCaja.Estado.ANULADO.value
    if nota:
        vale.nota = (vale.nota + "\n" + nota).strip()
    vale.save()
    return vale
