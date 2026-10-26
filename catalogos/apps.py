"""Configuración de la aplicación catalogos."""

from __future__ import annotations

from django.apps import AppConfig


class Configuracion(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "catalogos"
