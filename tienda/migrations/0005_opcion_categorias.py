"""Pone las categorías de la tienda en el menú, antes de los pedidos.

Hasta ahora las categorías solo se podían crear en el admin. Con su opción propia
—``categorias_tienda``— se crean y se corrigen desde la aplicación, dentro del
apartado Tienda.
"""

from __future__ import annotations

from django.db import migrations

NOMBRE = "Tienda"
ORDEN = 10

OPCION = {
    "clave": "categorias_tienda",
    "nombre": "Categorías de la tienda",
    "grupo": NOMBRE,
    "orden": ORDEN,
    "url": "/tienda/categorias/",
    "icono": "folder",
    "en_menu": True,
    "activo": True,
}


def sembrar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    tienda, _ = Categoria.objects.get_or_create(
        nombre=NOMBRE, defaults={"orden": 42, "icono": "shop", "activa": True}
    )
    Opcion.objects.update_or_create(
        clave=OPCION["clave"], defaults={**OPCION, "categoria": tienda}
    )
    # Los pedidos van después de las categorías dentro del apartado.
    Opcion.objects.filter(clave="pedidos").update(orden=ORDEN + 1)


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave=OPCION["clave"]).delete()
    Opcion.objects.filter(clave="pedidos").update(orden=ORDEN)


class Migration(migrations.Migration):
    dependencies = [
        ("tienda", "0004_pedidos_en_su_apartado"),
        ("personalize_options", "0005_categorias_de_serie"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
