"""La aplicación de los comprobantes electrónicos que no son la factura."""

from django.apps import AppConfig


class ComprobantesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comprobantes"
    verbose_name = "comprobantes electrónicos"
