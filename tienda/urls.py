"""Las direcciones de la tienda pública: la que ve cualquiera.

Van en la raíz del dominio, sin sesión: portada, categorías, ficha, carrito y el
acuse del pedido. Lo de gestionar la tienda —categorías, pedidos, preguntas y
reseñas— está en ``tienda/urls_gestion.py``, detrás de ``/wadmin/``.
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "tienda"

urlpatterns = [
    path("", views.portada, name="portada"),
    path("c/<slug:slug>/", views.categoria, name="categoria"),
    path("p/<slug:slug>/", views.producto, name="producto"),
    path("p/<slug:slug>/preguntar/", views.preguntar, name="preguntar"),
    path("p/<slug:slug>/resenar/", views.resenar, name="resenar"),
    path("seguimiento/", views.seguimiento, name="seguimiento"),
    path("buscar/", views.buscar, name="buscar"),
    path("ofertas/", views.ofertas, name="ofertas"),
    path("carrito/", views.carrito, name="carrito"),
    path("carrito/agregar/", views.agregar, name="agregar"),
    path("carrito/actualizar/", views.actualizar_carrito, name="actualizar_carrito"),
    path("carrito/linea/", views.linea_carrito, name="linea_carrito"),
    path("confirmar/", views.confirmar, name="confirmar"),
    path("gracias/<uuid:referencia>/", views.gracias, name="gracias"),
]
