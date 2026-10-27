"""Pone las preguntas y las reseñas en el apartado Tienda.

Son dos pantallas nuevas, con su permiso: quien las tenga en su rol las ve en el
menú; quien no, ni las ve ni puede abrirlas.
"""

from __future__ import annotations

from django.db import migrations

NOMBRE = "Tienda"

OPCIONES = (
    {
        "clave": "preguntas_tienda",
        "nombre": "Preguntas de la tienda",
        "orden": 12,
        "url": "/tienda/preguntas/",
        "icono": "chat",
    },
    {
        "clave": "resenas_tienda",
        "nombre": "Reseñas de la tienda",
        "orden": 13,
        "url": "/tienda/resenas/",
        "icono": "comment",
    },
)


def sembrar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    tienda, _ = Categoria.objects.get_or_create(
        nombre=NOMBRE, defaults={"orden": 42, "icono": "shop", "activa": True}
    )
    for datos in OPCIONES:
        Opcion.objects.update_or_create(
            clave=datos["clave"],
            defaults={
                **datos,
                "grupo": NOMBRE,
                "categoria": tienda,
                "en_menu": True,
                "activo": True,
            },
        )


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave__in=[datos["clave"] for datos in OPCIONES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tienda", "0006_pregunta_resena"),
        ("personalize_options", "0005_categorias_de_serie"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
