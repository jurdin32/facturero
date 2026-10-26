"""La supervisión de la caja en el menú y en los permisos.

Son dos opciones nuevas, con categoría propia: revisar los cuadres y manejar los
vales. No van dentro de «Caja del turno» porque no son del cajero —son de quien
controla— y así se pueden dar a un rol de supervisión sin darle la caja.
"""

from __future__ import annotations

from django.db import migrations

CATEGORIA = {
    "nombre": "Supervisión",
    "descripcion": "Revisar los cuadres de caja y cobrar los faltantes con vales.",
    "orden": 55,
    "icono": "checkmark",
}

OPCIONES = (
    ("revision_caja", "Revisión de caja", "/supervision/cuadres/", "checkmark", 1),
    ("vales_caja", "Vales de caja", "/supervision/vales/", "money", 2),
)


def sembrar(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    categoria, _ = Categoria.objects.update_or_create(
        nombre=CATEGORIA["nombre"],
        defaults={
            "descripcion": CATEGORIA["descripcion"],
            "orden": CATEGORIA["orden"],
            "icono": CATEGORIA["icono"],
            "activa": True,
        },
    )
    for clave, nombre, url, icono, orden in OPCIONES:
        Opcion.objects.update_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "categoria": categoria,
                "grupo": categoria.nombre,
                "orden": orden,
                "url": url,
                "icono": icono,
                "en_menu": True,
                "activo": True,
            },
        )


def deshacer(apps, schema_editor):
    Categoria = apps.get_model("personalize_options", "Categoria")
    Opcion = apps.get_model("personalize_options", "Opcion")

    Opcion.objects.filter(clave__in=[fila[0] for fila in OPCIONES]).delete()
    Categoria.objects.filter(nombre=CATEGORIA["nombre"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("caja", "0003_revision_y_vales"),
        ("personalize_options", "0005_categorias_de_serie"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
