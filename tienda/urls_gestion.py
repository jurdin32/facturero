"""Las direcciones de la trastienda: lo que se administra desde la aplicación.

Vive detrás de ``/wadmin/tienda/``, con sesión y con los permisos de la tienda.
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "gestion_tienda"

urlpatterns = [
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
