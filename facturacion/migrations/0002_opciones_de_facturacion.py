"""Pone la lista de facturas en el menú y en los permisos.

La pantalla ya se podía ver, pero su opción no estaba en la tabla del paquete de
seguridad: el menú enseñaba un enlace suelto —el de ``lista_factura``, que quedó de
una versión anterior— y la vista no pedía permiso. Ahora la opción es ``facturas``,
como el nombre de la dirección, y la de antes se retira.
"""

from __future__ import annotations

from django.db import migrations

OPCIONES = (
    ("tablero", "Tablero", "Resumen", "/", "dashboard", 1),
    ("facturar", "Nueva factura", "Facturar", "/facturar/", "plus", 1),
    ("facturas", "Facturas emitidas", "Facturar", "/facturas/", "books", 2),
)


def sembrar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    for clave, nombre, grupo, url, icono, orden in OPCIONES:
        Opcion.objects.update_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "grupo": grupo,
                "orden": orden,
                "url": url,
                "icono": icono,
                "en_menu": True,
                "activo": True,
            },
        )
    # La clave vieja apuntaba a la misma pantalla: si queda, el menú la enseña dos
    # veces y los permisos se reparten entre dos nombres.
    Opcion.objects.filter(clave="lista_factura").delete()


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    Opcion.objects.filter(clave__in=[fila[0] for fila in OPCIONES]).delete()
    Opcion.objects.update_or_create(
        clave="lista_factura",
        defaults={
            "nombre": "Lista de Facturas",
            "grupo": "Facturar",
            "orden": 2,
            "url": "/facturas/lista/",
            "icono": "books",
            "en_menu": True,
            "activo": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0001_initial"),
        ("personalize_options", "0003_sembrar_opciones"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
