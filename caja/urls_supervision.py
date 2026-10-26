"""Direcciones de la supervisión de caja.

La revisión de los cuadres y los vales no son cosa del cajero: son el control de
quien supervisa. Por eso viven aparte, en ``/supervision/``, con sus propios
permisos —``revision_caja`` y ``vales_caja``—, y no dentro de la pantalla del
turno.
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "supervision"

urlpatterns = [
    # Los turnos cerrados, para aprobarlos o dejarlos observados.
    path("cuadres/", views.revision, name="cuadres"),
    # El libro de vales: lo que se cobra y lo que ya se cobró.
    path("vales/", views.vales, name="vales"),
    path("vales/nuevo/", views.vale_nuevo, name="vale_nuevo"),
    path("vales/nuevo/<int:pk>/", views.vale_nuevo, name="vale_de_la_sesion"),
]
