"""Direcciones de la caja."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "caja"

urlpatterns = [
    path("", views.tablero, name="tablero"),
    # El acta de cierre, en PDF: el respaldo firmado del arqueo.
    path("acta/<int:pk>/", views.acta, name="acta"),
]
