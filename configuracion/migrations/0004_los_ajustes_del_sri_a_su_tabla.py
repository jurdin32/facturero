"""Los ajustes del SRI pasan a la tabla del paquete.

Los paquetes son independientes: ``factec`` guarda sus ajustes en
``sri_fe_ajustedelsri``, no en la tabla de ajustes del proyecto. Aquí se lleva allí
la clave de cifrado —para que el certificado se siga descifrando— y se borran de la
tabla del proyecto las filas ``sri_*``, que ya no se leen de ahí.
"""

from __future__ import annotations

from django.db import migrations

CLAVE_CIFRADO = "sri_clave_cifrado"


def mover(apps, schema_editor):
    Ajuste = apps.get_model("personalize_options", "Ajuste")
    AjusteDelSri = apps.get_model("sri_fe", "AjusteDelSri")

    viejo = Ajuste.objects.filter(clave=CLAVE_CIFRADO).first()
    nuevo, _ = AjusteDelSri.objects.get_or_create(
        clave=CLAVE_CIFRADO,
        defaults={
            "valor": "",
            "tipo": "texto",
            "grupo": "Seguridad",
            "orden": 9,
            "editable": False,
            "descripcion": (
                "Clave con la que se cifra la contraseña del certificado. No se "
                "enseña ni se edita desde el admin."
            ),
        },
    )
    if viejo is not None and viejo.valor and not nuevo.valor:
        nuevo.valor = viejo.valor
        nuevo.save(update_fields=["valor"])

    Ajuste.objects.filter(clave__startswith="sri_").delete()


def volver(apps, schema_editor):
    """Al volver atrás se reponen las filas del SRI en la tabla del proyecto."""
    Ajuste = apps.get_model("personalize_options", "Ajuste")
    AjusteDelSri = apps.get_model("sri_fe", "AjusteDelSri")

    for fila in AjusteDelSri.objects.all():
        Ajuste.objects.update_or_create(
            clave=fila.clave,
            defaults={
                "valor": fila.valor,
                "tipo": fila.tipo,
                "grupo": fila.grupo,
                "descripcion": fila.descripcion,
                "orden": fila.orden,
                "editable": fila.editable,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("configuracion", "0003_clave_de_cifrado"),
        ("personalize_options", "0007_alter_ajuste_options_ajuste_origen_and_more"),
        ("sri_fe", "0015_ajustes_del_sri"),
    ]

    operations = [migrations.RunPython(mover, volver)]
