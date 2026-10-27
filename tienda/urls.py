"""Las direcciones de la tienda.

Las de comprar van sin sesión: portada, categorías, ficha, carrito y el acuse del
pedido. Las de gestionar los pedidos viven bajo ``/pedidos/`` y piden permiso.
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "tienda"

urlpatterns = [
    # La tienda pública.
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
    path("confirmar/", views.confirmar, name="confirmar"),
    path("gracias/<uuid:referencia>/", views.gracias, name="gracias"),
    # Las categorías y los pedidos, desde la aplicación.
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nueva/", views.categoria_form, name="categoria_nueva"),
    path("categorias/<int:pk>/", views.categoria_form, name="categoria_editar"),
    path("preguntas/", views.preguntas, name="preguntas"),
    path("preguntas/<int:pk>/responder/", views.responder_pregunta, name="responder_pregunta"),
    path("preguntas/<int:pk>/publicar/", views.publicar_pregunta, name="publicar_pregunta"),
    path("resenas/", views.resenas, name="resenas"),
    path("resenas/<int:pk>/moderar/", views.moderar_resena, name="moderar_resena"),
    path("pedidos/", views.pedidos, name="pedidos"),
    path("pedidos/<int:pk>/", views.pedido, name="pedido"),
    path("pedidos/<int:pk>/facturar/", views.facturar, name="facturar"),
    path("pedidos/<int:pk>/anular/", views.anular, name="anular"),
]
