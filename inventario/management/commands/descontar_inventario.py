"""Descuenta del inventario las facturas autorizadas que quedaron sin descontar.

Cuando la emisión la hace el worker de Celery o el admin, el descuento automático
no llega: este comando recoge esas facturas y las descuenta, una sola vez cada una.

    python manage.py descontar_inventario --simular   # ver qué haría
    python manage.py descontar_inventario             # hacerlo
    python manage.py descontar_inventario --factura 12
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from ...models import Movimiento
from ...servicios import descuento_activo, facturas_sin_descontar, quedaron_en_negativo

__all__ = ["Command"]


class Command(BaseCommand):
    help = "Descuenta del inventario las facturas autorizadas a las que les falta el movimiento."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Solo decir qué haría, sin tocar el inventario.",
        )
        parser.add_argument(
            "--factura", type=int, default=None, help="Una sola factura, por su número de id."
        )

    def handle(self, *args: Any, **opciones: Any) -> str:
        simulando = bool(opciones.get("simular"))
        facturas = list(facturas_sin_descontar(opciones.get("factura")))

        if not facturas:
            self.stdout.write("No hay facturas autorizadas pendientes de descontar.")
            return ""

        if not descuento_activo() and not simulando:
            self.stdout.write(
                self.style.WARNING(
                    "El descuento automático está apagado en los ajustes "
                    "(INVENTARIO_DESCONTAR_AL_FACTURAR); se hace porque se pidió a mano."
                )
            )

        creados = 0
        for factura in facturas:
            comprobante = factura.comprobante
            serie = f"{comprobante.estab}-{comprobante.pto_emi}-{comprobante.secuencial}"
            if simulando:
                self.stdout.write(f"  {serie} · {factura.receptor.razon_social}")
                continue
            movimientos = Movimiento.salida_por_factura(factura)
            creados += len(movimientos)
            self.stdout.write(f"  {serie} · {factura.receptor.razon_social} · {len(movimientos)} línea(s)")
            for existencia in quedaron_en_negativo(movimientos):
                self.stdout.write(
                    self.style.WARNING(
                        f"    {existencia.producto.codigo_principal} quedó en "
                        f"{existencia.cantidad}: revise si falta una entrada."
                    )
                )

        if simulando:
            self.stdout.write(f"Se descontarían {len(facturas)} factura(s).")
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{len(facturas)} factura(s) descontada(s), {creados} movimiento(s) en el libro."
                )
            )
        return ""
