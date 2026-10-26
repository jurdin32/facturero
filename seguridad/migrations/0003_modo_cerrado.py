"""La instalación queda en modo cerrado: sólo lo que los roles permitan.

El paquete viene en «abierto» para poder montar la seguridad sin dejar a nadie
fuera; en este proyecto los roles ya están puestos, así que el ajuste se siembra en
«cerrado». Se cambia desde la administración (Ajustes → `modo`) sin tocar código.
"""

from __future__ import annotations

from django.db import migrations


def cerrar(apps, schema_editor):
    Ajuste = apps.get_model("personalize_options", "Ajuste")
    Ajuste.objects.update_or_create(
        clave="modo",
        defaults={
            "valor": "cerrado",
            "tipo": "texto",
            "grupo": "Seguridad",
            "orden": 1,
            "editable": True,
            "descripcion": (
                "«abierto»: quien no tenga ningún rol puede todo. «cerrado»: solo lo que "
                "los roles permitan."
            ),
        },
    )


def abrir(apps, schema_editor):
    Ajuste = apps.get_model("personalize_options", "Ajuste")
    Ajuste.objects.filter(clave="modo").update(valor="abierto")


class Migration(migrations.Migration):
    dependencies = [
        ("seguridad", "0002_categorias_de_las_opciones"),
        ("personalize_options", "0006_ajustes"),
    ]

    operations = [migrations.RunPython(cerrar, abrir)]
