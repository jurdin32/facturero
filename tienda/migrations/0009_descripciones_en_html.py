"""Las descripciones que se escribieron en Markdown pasan a ser HTML.

El editor ya es visual y guarda HTML; lo que había antes son marcas de Markdown.
Se convierten una vez aquí para que nadie se quede con ellas a la vista.
"""

from __future__ import annotations

import re

from django.db import migrations

#: Lo que delata que un texto ya viene en HTML y no en Markdown.
ES_HTML = re.compile(r"<\s*(p|div|br|table|h[2-6]|ul|ol|li|strong|em|blockquote|pre)\b", re.I)


def pasar_a_html(apps, schema_editor):
    from tienda.texto import markdown_a_html

    ProductoTienda = apps.get_model("tienda", "ProductoTienda")
    for tienda in ProductoTienda.objects.exclude(descripcion_larga="").iterator():
        texto = tienda.descripcion_larga or ""
        if ES_HTML.search(texto):
            continue
        tienda.descripcion_larga = str(markdown_a_html(texto))
        tienda.save(update_fields=["descripcion_larga"])


def volver_a_markdown(apps, schema_editor):
    """No se puede deshacer con fidelidad: el HTML no dice cómo se escribió."""


class Migration(migrations.Migration):
    dependencies = [("tienda", "0008_imagenproducto_es_video_alter_imagenproducto_imagen")]

    operations = [migrations.RunPython(pasar_a_html, volver_a_markdown)]
