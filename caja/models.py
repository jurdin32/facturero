"""Apertura, movimientos y cierre de caja por usuario.

Cada usuario abre su propia caja al empezar el turno y la cierra al terminar. El
saldo esperado son el saldo inicial más los ingresos menos los egresos; al cerrar
se compara con el efectivo contado y queda registrada la diferencia.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

CERO = Decimal("0.00")


class SesionCaja(models.Model):
    """Un turno de caja: desde que se abre hasta que se cierra."""

    class Estado(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.PROTECT,
        related_name="sesiones_caja",
    )
    estado = models.CharField(
        "estado", max_length=10, choices=Estado.choices, default=Estado.ABIERTA
    )
    saldo_inicial = models.DecimalField(
        "saldo inicial", max_digits=14, decimal_places=2, default=CERO
    )
    saldo_declarado = models.DecimalField(
        "efectivo contado al cerrar",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    desglose = models.JSONField(
        "desglose del efectivo",
        default=dict,
        blank=True,
        help_text="Cuántos billetes y monedas de cada valor se contaron al cerrar.",
    )
    abierta_en = models.DateTimeField("abierta", default=timezone.now)
    cerrada_en = models.DateTimeField("cerrada", null=True, blank=True)
    observaciones = models.TextField("observaciones de apertura", blank=True)
    observaciones_cierre = models.TextField("observaciones de cierre", blank=True)
    revision = models.CharField(
        "revisión",
        max_length=12,
        choices=(
            ("sin_revisar", "Sin revisar"),
            ("aprobada", "Aprobada"),
            ("observada", "Observada"),
        ),
        default="sin_revisar",
        help_text="Lo que dijo quien revisó el cuadre.",
    )
    revisada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="revisada por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cajas_revisadas",
    )
    revisada_en = models.DateTimeField("revisada", null=True, blank=True)
    nota_revision = models.TextField("nota de la revisión", blank=True)
    creado = models.DateTimeField("creada", auto_now_add=True)
    actualizado = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "sesión de caja"
        verbose_name_plural = "sesiones de caja"
        ordering = ["-abierta_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario"],
                condition=Q(estado="abierta"),
                name="caja_una_abierta_por_usuario",
            )
        ]

    def __str__(self) -> str:
        return f"Caja de {self.usuario.get_username()} · {self.get_estado_display()}"

    @property
    def abierta(self) -> bool:
        return self.estado == self.Estado.ABIERTA.value

    @property
    def total_ingresos(self) -> Decimal:
        return self.movimientos.filter(tipo=MovimientoCaja.Tipo.INGRESO.value).aggregate(
            total=models.Sum("importe")
        )["total"] or CERO

    @property
    def total_egresos(self) -> Decimal:
        return self.movimientos.filter(tipo=MovimientoCaja.Tipo.EGRESO.value).aggregate(
            total=models.Sum("importe")
        )["total"] or CERO

    @property
    def saldo_esperado(self) -> Decimal:
        return self.saldo_inicial + self.total_ingresos - self.total_egresos

    @property
    def diferencia(self) -> Decimal:
        if self.saldo_declarado is None:
            return CERO
        return self.saldo_declarado - self.saldo_esperado

    def clean(self) -> None:
        super().clean()
        if self.saldo_inicial is not None and self.saldo_inicial < CERO:
            raise ValidationError({"saldo_inicial": "El saldo inicial no puede ser negativo."})

    def cerrar(
        self,
        saldo_declarado: Decimal,
        observaciones: str = "",
        desglose: dict[str, int] | None = None,
    ) -> None:
        if not self.abierta:
            raise ValidationError("Esta caja ya está cerrada.")
        if saldo_declarado is None or saldo_declarado < CERO:
            raise ValidationError("El efectivo contado no puede ser negativo.")
        self.estado = self.Estado.CERRADA.value
        self.cerrada_en = timezone.now()
        self.saldo_declarado = saldo_declarado
        self.observaciones_cierre = observaciones
        if desglose:
            self.desglose = {clave: int(cantidad) for clave, cantidad in desglose.items() if cantidad}
        self.save()

    @property
    def renglones_del_desglose(self) -> list[dict[str, Any]]:
        """El desglose del cierre con sus subtotales, de mayor a menor."""
        from .servicios import DENOMINACIONES

        renglones = []
        for valor in DENOMINACIONES:
            cantidad = int((self.desglose or {}).get(str(valor), 0) or 0)
            renglones.append(
                {
                    "valor": valor,
                    "cantidad": cantidad,
                    "subtotal": valor * cantidad,
                    "es_billete": valor >= 1,
                }
            )
        return renglones


class MovimientoCaja(models.Model):
    """Un ingreso o un egreso de efectivo dentro de una sesión."""

    class Tipo(models.TextChoices):
        INGRESO = "ingreso", "Ingreso"
        EGRESO = "egreso", "Egreso"

    sesion = models.ForeignKey(
        SesionCaja, verbose_name="sesión", on_delete=models.CASCADE, related_name="movimientos"
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    concepto = models.CharField("concepto", max_length=200)
    referencia = models.CharField("referencia", max_length=120, blank=True)
    importe = models.DecimalField("importe", max_digits=14, decimal_places=2)
    fecha = models.DateTimeField("fecha", default=timezone.now)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="registrado por",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movimientos_caja",
    )
    comprobante = models.ForeignKey(
        "sri_fe.ComprobanteEmitido",
        verbose_name="comprobante",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movimientos_caja",
    )

    class Meta:
        verbose_name = "movimiento de caja"
        verbose_name_plural = "movimientos de caja"
        ordering = ["-fecha", "-pk"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.concepto} · {self.importe:.2f}"

    def clean(self) -> None:
        super().clean()
        if self.importe is None or self.importe <= CERO:
            raise ValidationError({"importe": "El importe debe ser mayor que cero."})

    @property
    def signo(self) -> str:
        return "+" if self.tipo == self.Tipo.INGRESO.value else "−"


class ValeCaja(models.Model):
    """Un vale de caja: el papel con el que se saca dinero del turno o se cobra un
    faltante.

    Sirve para dos cosas, que son las dos caras del mismo papel: **sacar** efectivo
    de la caja a cuenta de alguien (un anticipo, un gasto por reponer) o **cobrar**
    un saldo en contra, que es el faltante que apareció al cerrar el turno. Nace
    pendiente y se cierra cuando se cobra —o se anula, si no había por qué—.
    """

    class Tipo(models.TextChoices):
        FALTANTE = "faltante", "Faltante por cobrar"
        ANTICIPO = "anticipo", "Vale de anticipo"
        GASTO = "gasto", "Gasto por reponer"
        OTRO = "otro", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        COBRADO = "cobrado", "Cobrado"
        ANULADO = "anulado", "Anulado"

    numero = models.CharField("número", max_length=12, unique=True, blank=True)
    sesion = models.ForeignKey(
        SesionCaja,
        verbose_name="sesión",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vales",
        help_text="El turno en el que apareció el faltante o del que salió el efectivo.",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="responsable",
        on_delete=models.PROTECT,
        related_name="vales_de_caja",
        help_text="A quién se le cobra o a cuenta de quién va el vale.",
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.FALTANTE)
    motivo = models.CharField("motivo", max_length=200)
    importe = models.DecimalField("importe", max_digits=14, decimal_places=2)
    estado = models.CharField(
        "estado", max_length=10, choices=Estado.choices, default=Estado.PENDIENTE
    )
    fecha = models.DateField("fecha", default=timezone.localdate)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vales_creados",
    )
    cobrado_en = models.DateField("cobrado el", null=True, blank=True)
    nota = models.TextField("nota", blank=True)
    creado = models.DateTimeField("creado", auto_now_add=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "vale de caja"
        verbose_name_plural = "vales de caja"
        ordering = ["-fecha", "-pk"]

    def __str__(self) -> str:
        etiqueta = self.numero or f"vale #{self.pk}"
        return f"{etiqueta} · {self.get_tipo_display()}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.numero:
            ultimo = (
                ValeCaja.objects.exclude(numero="")
                .order_by("-pk")
                .values_list("numero", flat=True)
                .first()
            )
            siguiente = 1
            if ultimo and ultimo[3:].isdigit():
                siguiente = int(ultimo[3:]) + 1
            self.numero = f"VC-{siguiente:06d}"
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.importe is not None and self.importe <= CERO:
            raise ValidationError({"importe": "El importe del vale debe ser mayor que cero."})
