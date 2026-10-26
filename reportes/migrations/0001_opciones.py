"""Las opciones del módulo de reportes y del manual.

Cada reporte es una opción más, aunque no salga en el menú: así el administrador
puede dar lectura de unos y negar otros, que es lo que se necesita cuando el
contador solo tiene que ver los libros y no las ventas por cliente, por ejemplo.
"""

from __future__ import annotations

from django.db import migrations

#: (clave, nombre, url, icono, orden)
DEL_MENU = (
    ("reportes", "Reportes y estadísticas", "/reportes/", "charts", 1),
)

DEL_MANUAL = (
    ("manual", "Manual del sistema", "/reportes/manual/", "help", 1),
)

#: Los reportes sueltos: van sin menú, para repartirlos por roles.
POR_REPORTE = (
    ("ventas", "Libro de ventas", "receipt"),
    ("ventas_por_dia", "Ventas por día", "bar-chart"),
    ("ventas_clientes", "Ventas por cliente", "account-circle"),
    ("ventas_productos", "Ventas por producto y servicio", "cart-product"),
    ("ventas_tarifas", "Ventas por tarifa de IVA", "money"),
    ("comprobantes", "Comprobantes emitidos", "description"),
    ("comprobantes_procesos", "Procesos de emisión", "charts"),
    ("retenciones", "Retenciones emitidas", "money"),
    ("compras", "Registro de compras", "cart-product"),
    ("libro_diario", "Libro diario", "books"),
    ("libro_mayor", "Libro mayor", "library"),
    ("balance", "Balance de comprobación", "balance"),
    ("resultados", "Estado de resultados", "calculate"),
    ("situacion", "Estado de situación financiera", "bank"),
    ("inventario_movimientos", "Movimientos de inventario", "storage"),
    ("inventario_existencias", "Existencias en bodega", "cube"),
)


def sembrar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")

    for clave, nombre, url, icono, orden in DEL_MENU:
        Opcion.objects.update_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "grupo": "Reportes",
                "orden": orden,
                "url": url,
                "icono": icono,
                "en_menu": True,
                "activo": True,
            },
        )

    for clave, nombre, url, icono, orden in DEL_MANUAL:
        Opcion.objects.update_or_create(
            clave=clave,
            defaults={
                "nombre": nombre,
                "grupo": "Ayuda",
                "orden": orden,
                "url": url,
                "icono": icono,
                "en_menu": True,
                "activo": True,
            },
        )

    for orden, (clave, nombre, icono) in enumerate(POR_REPORTE, start=10):
        Opcion.objects.update_or_create(
            clave=f"reporte_{clave}",
            defaults={
                "nombre": nombre,
                "grupo": "Reportes",
                "orden": orden,
                "url": f"/reportes/{clave}/",
                "icono": icono,
                "en_menu": False,
                "activo": True,
            },
        )


def retirar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    claves = [fila[0] for fila in DEL_MENU] + [fila[0] for fila in DEL_MANUAL]
    claves += [f"reporte_{fila[0]}" for fila in POR_REPORTE]
    Opcion.objects.filter(clave__in=claves).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("personalize_options", "0003_sembrar_opciones"),
    ]

    operations = [migrations.RunPython(sembrar, retirar)]
