"""Las estadísticas y los reportes del sistema."""

from django.apps import AppConfig


class ReportesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reportes"
    verbose_name = "Estadísticas y reportes"
