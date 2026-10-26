"""Carga en la base los códigos de retención del SRI.

La tabla sale del archivo oficial que el SRI publica en «Retenciones en la fuente».
Se puede volver a correr cuando el SRI publique una resolución nueva: los códigos
se actualizan, no se duplican.

    python manage.py cargar_codigos_retencion            # cargar o poner al día
    python manage.py cargar_codigos_retencion --simular  # ver qué haría
    python manage.py cargar_codigos_retencion --limpiar  # y quitar los que ya no están

El archivo de datos dice de dónde salió cada cosa (``meta``): la hoja, la
resolución y la fecha de descarga.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from ...models import CodigoRetencion

__all__ = ["Command"]

#: Donde vive la tabla, tal como se descargó del SRI.
DATOS = Path(__file__).resolve().parents[2] / "datos" / "retenciones_sri.json"


def _fecha(texto: str) -> date | None:
    if not texto:
        return None
    anio, mes, dia = (int(parte) for parte in texto.split("-"))
    return date(anio, mes, dia)


class Command(BaseCommand):
    help = "Carga los códigos de retención del SRI desde el archivo oficial."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--archivo",
            default=str(DATOS),
            help="El JSON con la tabla (por omisión, el que viene con el proyecto).",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Solo decir qué haría, sin tocar la base.",
        )
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help=(
                "Quitar los códigos que ya no están en el archivo. Se usa cuando el "
                "SRI deroga códigos: si no, se quedan y alguien los elige."
            ),
        )

    def handle(self, *args: Any, **opciones: Any) -> str:
        ruta = Path(opciones["archivo"])
        if not ruta.exists():
            raise CommandError(f"No está el archivo de la tabla: {ruta}")

        datos = json.loads(ruta.read_text(encoding="utf-8"))
        meta = datos.get("meta") or {}
        codigos = datos.get("codigos") or []
        if not codigos:
            raise CommandError("El archivo no trae ningún código.")

        desde = _fecha(meta.get("vigente_desde", ""))
        simulando = bool(opciones.get("simular"))
        nuevos, puestos = 0, 0

        for fila in codigos:
            valores = {
                "concepto": fila["concepto"].strip(),
                "impuesto": fila.get("impuesto") or "1",
                "porcentaje": (
                    Decimal(str(fila["porcentaje"]))
                    if fila.get("porcentaje") is not None
                    else None
                ),
                "porcentaje_texto": fila.get("porcentaje_texto", ""),
                "vigente_desde": desde,
                "orden": fila.get("orden", 0),
            }
            if simulando:
                if CodigoRetencion.objects.filter(codigo=fila["codigo"]).exists():
                    puestos += 1
                else:
                    nuevos += 1
                continue
            _, creado = CodigoRetencion.objects.update_or_create(
                codigo=fila["codigo"], defaults=valores
            )
            if creado:
                nuevos += 1
            else:
                puestos += 1

        if simulando:
            self.stdout.write(
                f"Haría {nuevos} nuevo(s) y pondría al día {puestos}, "
                f"sin tocar la base."
            )
        else:
            sobran = 0
            if opciones.get("limpiar"):
                vigentes = [fila["codigo"] for fila in codigos]
                sobran, _ = (
                    CodigoRetencion.objects.exclude(codigo__in=vigentes).delete()
                )
            mensaje = (
                f"{nuevos} código(s) nuevo(s) y {puestos} al día. "
                f"Total: {CodigoRetencion.objects.count()}."
            )
            if sobran:
                mensaje += f" Se quitaron {sobran} que ya no están en la tabla."
            self.stdout.write(self.style.SUCCESS(mensaje))
        if meta.get("normativa"):
            self.stdout.write(f"Normativa: {meta['normativa']}")
        return ""
