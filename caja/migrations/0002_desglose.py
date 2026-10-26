"""La migración que guarda el desglose del efectivo al cerrar la caja."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("caja", "0002_opciones"),
    ]

    operations = [
        migrations.AddField(
            model_name="sesioncaja",
            name="desglose",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Cuántos billetes y monedas de cada valor se contaron al cerrar.",
                verbose_name="desglose del efectivo",
            ),
        ),
    ]
