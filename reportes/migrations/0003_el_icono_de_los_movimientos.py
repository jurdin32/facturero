"""El icono de «Movimientos de inventario» ya está en la fuente.

Se sembró con ``storage``, que la fuente de iconos no trae: la caja del menú salía
vacía. Ahora usa ``database``, que sí dibuja.
"""

from __future__ import annotations

from django.db import migrations

VIEJO = "storage"
NUEVO = "database"


def arreglar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(icono=VIEJO).update(icono=NUEVO)


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(icono=NUEVO).update(icono=VIEJO)


class Migration(migrations.Migration):
    dependencies = [
        ("reportes", "0002_opcion_ventas_por_usuario"),
        ("personalize_options", "0002_opcion"),
    ]

    operations = [migrations.RunPython(arreglar, deshacer)]
