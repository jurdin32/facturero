"""Configuración de la aplicación inventario."""

from __future__ import annotations

from django.apps import AppConfig


class Configuracion(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventario"

    def ready(self) -> None:
        """Declara su ajuste: lo que se puede cambiar sin tocar código.

        Al migrar queda sembrado en la tabla de ajustes (ver
        ``personalize_options.ajustes``), así que no hay nada que poner en
        ``settings.py``.
        """
        from personalize_options.ajustes import AjusteDeSerie, registrar

        registrar(
            AjusteDeSerie(
                "inventario_descontar_al_facturar",
                "si",
                tipo="booleano",
                grupo="Inventario",
                orden=1,
                descripcion=(
                    "Al autorizarse una factura, descontar del inventario lo que lleva. "
                    "Con «no», el inventario solo se mueve a mano desde el libro."
                ),
            )
        )
