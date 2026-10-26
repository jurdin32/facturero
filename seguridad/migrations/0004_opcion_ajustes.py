"""La pantalla de ajustes, en el menú de Sistema.

La configuración de la aplicación se cambia desde la propia aplicación —no sólo
desde el admin—, así que es una opción más: sale en el menú para quien tenga
permiso y se marca en los roles como cualquier otra.
"""

from __future__ import annotations

from django.db import migrations

CLAVE = "ajustes"


def sembrar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    categoria = Categoria.objects.filter(nombre="Sistema").first()
    Opcion.objects.update_or_create(
        clave=CLAVE,
        defaults={
            "nombre": "Ajustes de la aplicación",
            "categoria": categoria,
            "grupo": categoria.nombre if categoria else "Sistema",
            "orden": 35,
            "url": "/seguridad/ajustes/",
            "icono": "cog",
            "en_menu": True,
            "activo": True,
        },
    )
    # La configuración del SRI pasa a ir después, para dejarle el sitio.
    Opcion.objects.filter(clave="configuracion").update(orden=36)


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave=CLAVE).delete()
    Opcion.objects.filter(clave="configuracion").update(orden=35)


class Migration(migrations.Migration):
    dependencies = [
        ("seguridad", "0003_modo_cerrado"),
        ("personalize_options", "0006_ajustes"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
