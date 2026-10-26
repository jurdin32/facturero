"""Los enlaces de las opciones que el menú dibuja a mano.

Las opciones de serie nacen sin dirección porque el menú las escribe en la
plantilla. Aquí se les pone la misma dirección para que la pantalla «Opciones de
la aplicación» las muestre completas y para que se puedan usar como permisos por
URL. Solo se rellenan las que estén vacías: si alguien cambia una dirección, una
migración posterior no se la pisa.
"""

from __future__ import annotations

from django.db import migrations

ENLACES = {
    "productos": "/catalogos/productos/",
    "clientes": "/catalogos/clientes/",
    "conductores": "/catalogos/conductores/",
    "vehiculos": "/catalogos/vehiculos/",
    "inventario": "/inventario/",
    "notas_credito": "/comprobantes/notas-credito/",
    "notas_debito": "/comprobantes/notas-debito/",
    "liquidaciones_compra": "/comprobantes/liquidaciones-compra/",
    "guias_remision": "/comprobantes/guias-remision/",
    "retenciones": "/comprobantes/retenciones/",
    "configuracion": "/configuracion/sri/",
    "roles": "/seguridad/",
    "usuarios": "/seguridad/usuarios/",
    "opciones": "/seguridad/opciones/",
}


def poner_enlaces(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")
    for clave, url in ENLACES.items():
        Opcion.objects.filter(clave=clave, url="").update(url=url)


class Migration(migrations.Migration):
    dependencies = [("personalize_options", "0003_sembrar_opciones")]

    operations = [migrations.RunPython(poner_enlaces, migrations.RunPython.noop)]
