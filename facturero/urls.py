"""Las direcciones del proyecto: cuatro aplicaciones y el admin.

El admin queda en ``/admin/`` para lo que se hace de vez en cuando (mirar los
comprobantes, los catálogos del SRI); el día a día se hace en las otras
pantallas, y la configuración del emisor y del SRI, en su asistente de cuatro
pasos (``/configuracion/sri/``).
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from . import sesion

urlpatterns = [
    # Entrar y salir (plantilla propia, en templates/).
    path(
        "entrar/",
        auth_views.LoginView.as_view(
            template_name="entrar.html", redirect_authenticated_user=True
        ),
        name="entrar",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="salir"),

    # La pantalla se bloquea sola cuando pasa un rato sin usarla. El botón de la
    # barra la bloquea cuando uno se va.
    path("bloquear/", sesion.bloquear, name="bloquear"),
    path("bloqueado/", sesion.bloquear_pantalla, name="bloquear_pantalla"),
    path("desbloquear/", sesion.desbloquear, name="desbloquear"),

    # Facturar (la pantalla principal, en la raíz).
    path("", include("facturacion.urls")),

    # Los demás comprobantes electrónicos del SRI, todos con las mismas pantallas.
    path("comprobantes/", include("comprobantes.urls")),

    # Catálogo e inventario.
    path("catalogos/", include("catalogos.urls")),
    path("inventario/", include("inventario.urls")),

    # La tienda en línea: el catálogo público y los pedidos que deja.
    path("tienda/", include("tienda.urls")),

    # Contabilidad: plan de cuentas, asientos, estados financieros y anexos SRI.
    path("contabilidad/", include("conta_ec.django.urls")),

    # Apertura, movimientos y cierre de caja por usuario.
    path("caja/", include("caja.urls")),

    # La supervisión de la caja: aprobar los cuadres y cobrar los faltantes con
    # vales. Es de quien controla, así que va aparte y con sus propios permisos.
    path("supervision/", include("caja.urls_supervision")),

    # La configuración del emisor y del SRI, en cuatro pasos.
    path("configuracion/", include("configuracion.urls")),

    # Los roles y quién los lleva (el paquete personalize_options guarda el cómo).
    path("seguridad/", include("seguridad.urls")),

    # Los reportes, las estadísticas y el manual del sistema.
    path("reportes/", include("reportes.urls")),

    path("admin/", admin.site.urls),
]

# En desarrollo el servidor también sirve lo que se sube —el logo del emisor—: sin
# esto la imagen del RIDE saldría rota. En producción lo pone el servidor web.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
