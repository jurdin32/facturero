"""Direcciones de la pantalla de facturación (es la pantalla principal)."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "facturacion"

urlpatterns = [
    # Lo primero que se ve al entrar: el tablero. La lista, en /facturas/.
    path("", views.tablero, name="tablero"),
    path("facturas/", views.facturas, name="facturas"),
    path("facturas/lista/", views.facturas, name="facturas_alt"),
    path("facturar/", views.facturar, name="facturar"),
    path("facturar/<int:pk>/", views.facturar, name="editar_factura"),
    path("factura/<int:pk>/", views.factura, name="factura"),
    path("factura/<int:pk>/accion/<str:que>/", views.accion, name="accion"),
    path("factura/<int:pk>/xml/", views.xml, name="xml"),
    path("factura/<int:pk>/xml/<str:cual>/", views.xml, name="xml_cual"),
    path("factura/<int:pk>/ride/", views.ride, name="ride"),
    path("producto/<int:pk>/datos/", views.producto, name="producto_datos"),
    path("productos/buscar/", views.buscar_productos, name="buscar_productos"),
    path("clientes/buscar/", views.buscar_clientes, name="buscar_clientes"),
]
