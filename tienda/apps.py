"""Configuración de la aplicación tienda."""

from __future__ import annotations

from django.apps import AppConfig


class Tienda(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tienda"
    verbose_name = "Tienda en línea"
