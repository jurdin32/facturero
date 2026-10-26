"""La contabilidad del negocio: plan de cuentas, asientos y anexos del SRI."""

from __future__ import annotations

from django.apps import AppConfig


class ContabilidadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contabilidad"
    verbose_name = "contabilidad"

    def ready(self) -> None:
        # La contabilización automática escucha lo que el SRI autoriza.
        from personalize_options.ajustes import AjusteDeSerie, registrar

        from . import signals  # noqa: F401

        registrar(
            AjusteDeSerie(
                "contabilidad_contabilizar_al_autorizar",
                "si",
                tipo="booleano",
                grupo="Contabilidad",
                orden=1,
                descripcion=(
                    "Al autorizarse un comprobante del SRI, armar su asiento con las cuentas "
                    "de la configuración contable."
                ),
            ),
            AjusteDeSerie(
                "contabilidad_periodo_automatico",
                "si",
                tipo="booleano",
                grupo="Contabilidad",
                orden=2,
                descripcion=(
                    "Abrir solo el período del mes de cada asiento. Con «no», los períodos "
                    "se abren a mano."
                ),
            ),
        )
