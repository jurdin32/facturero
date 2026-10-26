"""Configuración de la aplicación configuracion."""

from __future__ import annotations

from django.apps import AppConfig


class Configuracion(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "configuracion"
    verbose_name = "Configuración del SRI"
