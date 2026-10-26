"""Direcciones de los reportes.

``/reportes/`` es el índice; ``/reportes/<clave>/`` es cada reporte, y el formato se
pide con la query: ``?formato=pdf`` o ``?formato=xlsx``. El manual va antes que el
reporte genérico, si no «manual» se tomaría por una clave de reporte.
"""

from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.indice, name="indice"),
    path("manual/", views.manual_del_sistema, name="manual"),
    path("<str:clave>/", views.reporte, name="reporte"),
]
