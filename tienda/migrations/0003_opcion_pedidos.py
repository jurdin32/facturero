"""Pone los pedidos de la tienda en el menú y en los permisos.

La pantalla vive en ``/tienda/pedidos/`` y va con el permiso ``pedidos``: quien no
lo tenga no la ve en el menú ni puede abrirla. Queda dentro del apartado «Catálogo»,
junto a productos e inventario, que es donde se busca.
"""

from __future__ import annotations

from django.db import migrations

#: La opción, con lo que necesita el menú.
OPCION = {
    "clave": "pedidos",
    "nombre": "Pedidos de la tienda",
    "grupo": "Catálogo",
    "orden": 6,
    "url": "/tienda/pedidos/",
    "icono": "shop",
    "en_menu": True,
    "activo": True,
}


def sembrar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    categoria, _ = Categoria.objects.get_or_create(
        nombre="Catálogo", defaults={"orden": 30, "activa": True}
    )
    Opcion.objects.update_or_create(
        clave=OPCION["clave"],
        defaults={**OPCION, "categoria": categoria},
    )


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave=OPCION["clave"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tienda", "0002_pedido_lineapedido_pedido_tienda_pedido_fecha"),
        ("personalize_options", "0005_categorias_de_serie"),
        # Después de enlazar las categorías de las demás opciones.
        ("seguridad", "0002_categorias_de_las_opciones"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
