"""Configuración de la aplicación seguridad."""

from __future__ import annotations

from django.apps import AppConfig


class Configuracion(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "seguridad"
    verbose_name = "Seguridad"

    def ready(self) -> None:
        """Declara el ajuste del bloqueo de pantalla."""
        from personalize_options.ajustes import AjusteDeSerie, registrar

        registrar(
            AjusteDeSerie(
                "bloqueo_inactividad_minutos",
                "15",
                tipo="entero",
                grupo="Seguridad",
                orden=3,
                descripcion=(
                    "Minutos sin tocar la pantalla antes de bloquearla y pedir la clave otra "
                    "vez. Con 0 no se bloquea nunca."
                ),
            )
        )
