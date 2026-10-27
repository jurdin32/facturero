"""Pone «Pedidos de la tienda» en su propio apartado, después de Catálogo.

La opción se sembró dentro de Catálogo, pero la tienda no es un catálogo: tiene su
pantalla, su permiso y su sitio en el menú. El menú pone cada apartado donde va su
primera opción, así que para que la tienda caiga entre Catálogo (5–9) y Comprobantes
(10 en adelante) se corre un puesto todo lo que venía desde el 10 y se deja el 10
para Pedidos. El orden visible del resto no cambia.
"""

from __future__ import annotations

from django.db import migrations
from django.db.models import F

NOMBRE = "Tienda"
ORDEN = 42
CLAVE = "pedidos"
LUGAR = 10


def sembrar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    tienda, _ = Categoria.objects.update_or_create(
        nombre=NOMBRE,
        defaults={"orden": ORDEN, "icono": "shop", "activa": True},
    )
    # Se hace sitio en el 10: lo que estaba de ahí en adelante pasa un puesto más.
    Opcion.objects.filter(orden__gte=LUGAR).exclude(clave=CLAVE).update(orden=F("orden") + 1)
    Opcion.objects.filter(clave=CLAVE).update(
        categoria=tienda, grupo=NOMBRE, orden=LUGAR
    )


def deshacer(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    catalogo = Categoria.objects.filter(nombre="Catálogo").first()
    Opcion.objects.filter(clave=CLAVE).update(
        categoria=catalogo, grupo="Catálogo", orden=LUGAR + 1
    )
    Opcion.objects.filter(orden__gt=LUGAR).exclude(clave=CLAVE).update(orden=F("orden") - 1)
    Categoria.objects.filter(nombre=NOMBRE, opciones__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tienda", "0003_opcion_pedidos"),
        ("personalize_options", "0005_categorias_de_serie"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
