"""Deja cada opción dentro de su categoría de permisos.

Las opciones que siembran las migraciones de los proyectos llegan con el apartado
escrito y sin categoría, porque una migración guarda con el modelo tal como estaba en
ese momento. Aquí se enlazan con la categoría del mismo nombre: así el asistente del
rol las enseña dentro de su grupo y no queda ningún apartado suelto.

Es idempotente: se puede volver a correr sin cambiar nada.
"""

from __future__ import annotations

from django.db import migrations


def enlazar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    # Primero, una categoría por cada apartado que se haya quedado sin la suya: las
    # migraciones de los proyectos crean opciones después de la siembra del paquete.
    apartados = (
        Opcion.objects.exclude(grupo="")
        .filter(categoria__isnull=True)
        .values_list("grupo", flat=True)
        .distinct()
    )
    for nombre in apartados:
        Categoria.objects.get_or_create(
            nombre=nombre, defaults={"orden": 100 + len(nombre), "activa": True}
        )

    for categoria in Categoria.objects.all():
        Opcion.objects.filter(grupo=categoria.nombre, categoria__isnull=True).update(
            categoria=categoria
        )


def deshacer(apps, schema_editor):
    """No se deshace: quitar la categoría dejaría las opciones sin grupo visible."""


class Migration(migrations.Migration):
    dependencies = [
        ("personalize_options", "0005_categorias_de_serie"),
        ("seguridad", "0001_enlaces_del_menu"),
        # Al final de las siembras del proyecto, que son las que crean las opciones.
        ("reportes", "0002_opcion_ventas_por_usuario"),
        ("caja", "0002_opciones"),
        ("facturacion", "0002_opciones_de_facturacion"),
    ]

    operations = [migrations.RunPython(enlazar, deshacer)]
