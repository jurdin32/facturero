"""Las direcciones del proyecto: la tienda en la raíz y la aplicación en ``/wadmin/``.

Lo que ve un visitante —la tienda en línea— se atiende desde ``/``, sin sesión, para
que cualquiera pueda comprar. Todo lo de la empresa —facturar, catálogos,
inventario, contabilidad, caja, la configuración del SRI, el admin de Django y la
trastienda de la tienda— vive detrás de ``/wadmin/``, con su sesión y sus permisos.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from tienda import views as tienda_views

urlpatterns = [
    # Las direcciones de antes (``/tienda/...``) llevan a donde están ahora.
    path("tienda/", tienda_views.enlace_viejo),
    path("tienda/<path:resto>", tienda_views.enlace_viejo),
    path("entrar/", RedirectView.as_view(url="/wadmin/entrar/", permanent=True)),

    # La tienda en línea, pública, en la raíz del dominio.
    path("", include("tienda.urls")),

    # La aplicación, detrás de /wadmin/.
    path("wadmin/", include("facturero.urls_privado")),
]

# En desarrollo el servidor también sirve lo que se sube —el logo del emisor, las
# fotos de los productos—: sin esto las imágenes saldrían rotas. En producción lo
# pone el servidor web.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
