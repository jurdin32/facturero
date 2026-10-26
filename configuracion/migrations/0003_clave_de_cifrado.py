"""La clave de cifrado del certificado pasa a la base de datos.

Antes iba en ``settings.FACTURACION_ELECTRONICA['CLAVE_CIFRADO']``; `settings.py`
queda sólo con lo que es de Django y este valor —que ya estaba escrito en el
repositorio— se guarda como ajuste, para que la aplicación siga firmando sin tocar
código.

**En producción conviene moverla a la variable de entorno** ``SRI_CLAVE_CIFRADO``,
que manda sobre este ajuste: es la llave que protege la contraseña del certificado
y, si vive en la misma base que la contraseña cifrada, cifrarla pierde sentido.
"""

from __future__ import annotations

from django.db import migrations

#: La clave que tenía el proyecto en ``settings.py``.
CLAVE = "NGlZXdGnD9aUCI6J6Gvcbc7MKouW1ByH-gdUncbYmxM="


def sembrar(apps, schema_editor):
    Ajuste = apps.get_model("personalize_options", "Ajuste")
    if Ajuste.objects.filter(clave="sri_clave_cifrado").exists():
        return
    Ajuste.objects.create(
        clave="sri_clave_cifrado",
        valor=CLAVE,
        tipo="texto",
        grupo="Facturación electrónica",
        orden=9,
        editable=False,
        descripcion=(
            "Clave con la que se cifra la contraseña del certificado. Mejor en la "
            "variable de entorno SRI_CLAVE_CIFRADO."
        ),
    )


def deshacer(apps, schema_editor):
    Ajuste = apps.get_model("personalize_options", "Ajuste")
    Ajuste.objects.filter(clave="sri_clave_cifrado").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("configuracion", "0001_initial"),
        ("personalize_options", "0006_ajustes"),
    ]

    operations = [migrations.RunPython(sembrar, deshacer)]
