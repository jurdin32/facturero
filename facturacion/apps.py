"""Configuración de la aplicación facturacion."""

from __future__ import annotations

from django.apps import AppConfig


class Configuracion(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "facturacion"
