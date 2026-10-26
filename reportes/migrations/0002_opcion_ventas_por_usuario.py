"""La opción del reporte de ventas por usuario.

Va en su propia migración y no en la primera porque aquella ya está aplicada en las
bases que existen: una migración aplicada no se toca.
"""

from __future__ import annotations

from django.db import migrations


def sembrar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.update_or_create(
        clave="reporte_ventas_por_usuario",
        defaults={
            "nombre": "Ventas por usuario",
            "grupo": "Reportes",
            "orden": 13,
            "url": "/reportes/ventas_por_usuario/",
            "icono": "account-circle",
            "en_menu": False,
            "activo": True,
        },
    )


def retirar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave="reporte_ventas_por_usuario").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reportes", "0001_opciones"),
    ]

    operations = [migrations.RunPython(sembrar, retirar)]
