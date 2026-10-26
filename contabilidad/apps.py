"""La contabilidad del negocio: plan de cuentas, asientos y anexos del SRI."""

from __future__ import annotations

from django.apps import AppConfig


class ContabilidadConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contabilidad"
    verbose_name = "contabilidad"

    def ready(self) -> None:
        # La contabilización automática escucha lo que el SRI autoriza.
        from . import signals  # noqa: F401
