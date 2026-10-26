"""Direcciones del catálogo: productos, servicios, clientes y el transporte."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "catalogos"

urlpatterns = [
    path("productos/", views.productos, name="productos"),
    path("productos/nuevo/", views.producto, name="producto_nuevo"),
    path("productos/<int:pk>/", views.producto, name="producto"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente, name="cliente_nuevo"),
    path("clientes/consultar/", views.consultar_identificacion, name="consultar_identificacion"),
    path("clientes/identificar/", views.identificar_cliente, name="identificar_cliente"),
    path("clientes/<int:pk>/", views.cliente, name="cliente"),
    path("clientes/rapido/", views.cliente_nuevo, name="cliente_rapido"),
    # El transporte de la guía de remisión: quién lleva y en qué.
    path("conductores/", views.conductores, name="conductores"),
    path("conductores/nuevo/", views.conductor, name="conductor_nuevo"),
    path("conductores/<int:pk>/", views.conductor, name="conductor"),
    path("vehiculos/", views.vehiculos, name="vehiculos"),
    path("vehiculos/nuevo/", views.vehiculo, name="vehiculo_nuevo"),
    path("vehiculos/<int:pk>/", views.vehiculo, name="vehiculo"),
]
