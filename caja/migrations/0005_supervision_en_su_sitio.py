"""El apartado de Supervisión va en su sitio del menú.

Las opciones llevan un ``orden`` que sirve para dos cosas: ordenar las opciones
dentro de su apartado y ordenar los apartados entre sí (cada apartado va donde va
su primera opción). «Revisión de caja» y «Vales de caja» se sembraron con 1 y 2,
que es el sitio del Tablero y de la Caja: el apartado se colaba arriba. Aquí se
les da el sitio que les toca —después de Contabilidad, antes de Reportes— y se
corren dos puestos los que venían detrás.
"""

from __future__ import annotations

from django.db import migrations
from django.db.models import F

#: Los que iban detrás y se corren para dejar hueco.
DESPUES = ("reportes", "manual", "usuarios", "roles", "opciones", "configuracion")

#: El hueco que se abre: el orden que toman las dos opciones nuevas.
ORDEN = {"revision_caja": 28, "vales_caja": 29}


def sembrar(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")

    for clave in reversed(DESPUES):  # de abajo arriba, para no pisarse
        Opcion.objects.filter(clave=clave).update(orden=F("orden") + len(ORDEN))
    for clave, orden in ORDEN.items():
        Opcion.objects.filter(clave=clave).update(orden=orden)


def deshacer(apps, schema_editor):
    Opcion = apps.get_model("personalize_options", "Opcion")

    for clave in reversed(DESPUES):
        Opcion.objects.filter(clave=clave).update(orden=F("orden") - len(ORDEN))
    Opcion.objects.filter(clave="revision_caja").update(orden=1)
    Opcion.objects.filter(clave="vales_caja").update(orden=2)


class Migration(migrations.Migration):
    dependencies = [
        ("caja", "0004_supervision_de_caja"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
