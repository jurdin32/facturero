"""Pone la caja en el menú y en los permisos."""

from __future__ import annotations

from django.db import migrations

OPCIONES = (
    ("caja", "Caja del turno", "/caja/", "wallet", 1),
)


def sembrar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    for clave, nombre, url, icono, orden in OPCIONES:
        Opcion.objects.update_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "grupo": "Caja",
                "orden": orden,
                "url": url,
                "icono": icono,
                "en_menu": True,
                "activo": True,
            },
        )


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave__in=[fila[0] for fila in OPCIONES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("caja", "0001_initial"),
        ("personalize_options", "0003_sembrar_opciones"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
