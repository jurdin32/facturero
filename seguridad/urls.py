"""Direcciones de la seguridad: los roles y quién los lleva."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "seguridad"

urlpatterns = [
    path("", views.roles, name="roles"),
    path("roles/nuevo/", views.rol, name="rol_nuevo"),
    path("roles/<int:pk>/", views.rol, name="rol"),
    path("roles/<int:pk>/<str:que>/", views.accion, name="accion"),
    path("usuarios/", views.usuarios, name="usuarios"),
    # El alta desde la aplicación: el admin queda para lo de vez en cuando.
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:pk>/", views.usuario, name="usuario"),
    path("usuarios/<int:pk>/datos/", views.usuario_datos, name="usuario_datos"),
    # La configuración de la aplicación: lo que antes estaba en settings.py.
    path("ajustes/", views.ajustes, name="ajustes"),
    path("opciones/", views.opciones, name="opciones"),
    path("opciones/ordenar/", views.ordenar_menu, name="ordenar_menu"),
    path(
        "opciones/ordenar/guardar/",
        views.guardar_orden_menu,
        name="guardar_orden_menu",
    ),
    path("opciones/nueva/", views.opcion, name="opcion_nueva"),
    path("opciones/<int:pk>/", views.opcion, name="opcion"),
    path("opciones/<int:pk>/<str:que>/", views.accion_opcion, name="accion_opcion"),
]
