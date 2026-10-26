"""Las direcciones de los comprobantes electrónicos.

Todas siguen el mismo patrón y llevan el tipo en la dirección: la lista de las notas
de crédito es ``/comprobantes/notas-credito/``, su ficha ``.../<pk>/`` y su RIDE
``.../<pk>/ride/``. Así una plantilla no necesita saber de qué comprobante se trata.
"""

from django.urls import path

from . import views

app_name = "comprobantes"

urlpatterns = [
    # Los buscadores van antes: si no, «buscar» se tomaría por un tipo de comprobante.
    path("buscar/documentos/", views.buscar_documentos, name="buscar_documentos"),
    path("buscar/retenciones/", views.buscar_codigos_retencion, name="buscar_retenciones"),
    path("buscar/items/", views.items_de_documento, name="items_documento"),
    path("<str:clave>/", views.lista, name="lista"),
    path("<str:clave>/nuevo/", views.formulario, name="nuevo"),
    path("<str:clave>/<int:pk>/", views.ficha, name="ficha"),
    path("<str:clave>/<int:pk>/editar/", views.formulario, name="editar"),
    path("<str:clave>/<int:pk>/ride/", views.ride, name="ride"),
    path("<str:clave>/<int:pk>/documento/<str:cual>/", views.documento_sri, name="documento"),
    path("<str:clave>/<int:pk>/accion/<str:que>/", views.accion, name="accion"),
]
