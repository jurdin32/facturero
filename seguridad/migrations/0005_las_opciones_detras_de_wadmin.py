"""Las opciones del menú apuntan a las direcciones nuevas.

La aplicación se mudó detrás de ``/wadmin/`` para dejar la raíz del dominio a la
tienda pública. Las opciones del menú son datos —cada una guarda su dirección—, así
que las que ya estaban sembradas se quedan con las de antes y el menú lleva a un
sitio que ya no existe. Aquí se les pone el prefijo.
"""

from __future__ import annotations

from django.db import migrations

#: Lo que ahora va delante de todas las pantallas de la aplicación.
PREFIJO = "/wadmin"


def mover(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    for opcion in Opcion.objects.all().only("id", "url"):
        url = (opcion.url or "").strip()
        if not url.startswith("/") or url.startswith(PREFIJO + "/") or url == PREFIJO:
            continue
        opcion.url = PREFIJO + url
        opcion.save(update_fields=["url"])


def devolver(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    for opcion in Opcion.objects.all().only("id", "url"):
        url = (opcion.url or "").strip()
        if not url.startswith(PREFIJO + "/"):
            continue
        opcion.url = url[len(PREFIJO):] or "/"
        opcion.save(update_fields=["url"])


class Migration(migrations.Migration):
    dependencies = [
        ("seguridad", "0004_opcion_ajustes"),
        ("tienda", "0009_descripciones_en_html"),
    ]

    operations = [migrations.RunPython(mover, devolver)]
