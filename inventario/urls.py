"""Direcciones del inventario: existencias y el libro de movimientos."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.inventario, name="inventario"),
    path("producto/<int:pk>/", views.kardex, name="kardex"),
    path("producto/<int:pk>/movimiento/", views.movimiento_nuevo, name="movimiento_nuevo"),
    path("movimiento/<int:pk>/anular/", views.movimiento_anular, name="movimiento_anular"),
]
