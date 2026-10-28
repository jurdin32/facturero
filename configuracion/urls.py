"""Direcciones del asistente de configuración del SRI."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "configuracion"

urlpatterns = [
    # El asistente: el paso se pide con ?paso=1..4 y la configuración con ?c=<pk>.
    path("sri/", views.sri, name="sri"),
    path("sri/otra/", views.otra, name="otra"),
    # Elegir cuál se usa: la de pruebas o la de producción (solo una, siempre).
    path("sri/<int:pk>/usar/", views.activar, name="activar"),
    path("sri/logo/", views.logo, name="logo"),
    path("sri/probar/", views.probar_sri, name="probar_sri"),
]
