"""El bloqueo de la pantalla por inactividad.

La sesión no se cierra: se **bloquea**. Cualquier petición con la sesión bloqueada
—o con la inactividad pasada de largo— recibe la pantalla de bloqueo en lugar de
lo que pedía, así que recargar o volver con el historial no la esquiva. Se
desbloquea escribiendo la clave del mismo usuario, en la pantalla de bloqueo.

Con ``BLOQUEO_INACTIVIDAD_MINUTOS = 0`` no se bloquea nada.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

#: Clave de la sesión con la marca de la última vez que el usuario hizo algo.
ULTIMA = "ultima_actividad"
#: Clave de la sesión que dice si la pantalla está bloqueada.
BLOQUEADA = "bloqueada"

#: La aplicación vive detrás de esta ruta; lo demás —la tienda— es público y no se
#: bloquea nunca.
PRIVADO = "/wadmin/"

#: Rutas que se atienden aunque la pantalla esté bloqueada (si no, no habría forma
#: de desbloquear ni de cargar la propia pantalla).
EXENTAS = (
    "/wadmin/entrar/",
    "/wadmin/salir/",
    "/wadmin/bloquear/",
    "/wadmin/desbloquear/",
    "/wadmin/admin/jsi18n/",
    "/static/",
    "/media/",
    "/favicon.ico",
)


def minutos_de_bloqueo() -> int:
    """Minutos de inactividad que aguanta la pantalla sin bloquearse.

    Sale de los ajustes de la aplicación (``bloqueo_inactividad_minutos``), que se
    cambian desde la administración sin tocar código.
    """
    from personalize_options import ajustes

    return max(0, ajustes.entero("bloqueo_inactividad_minutos", 15))


def _exenta(ruta: str) -> bool:
    if not ruta.startswith(PRIVADO):
        return True
    return any(ruta.startswith(prefijo) for prefijo in EXENTAS)


def _marca(valor: Any) -> Optional[datetime]:
    """Convierte lo guardado en la sesión en una fecha con zona."""
    if isinstance(valor, datetime):
        fecha: Optional[datetime] = valor
    elif isinstance(valor, str):
        fecha = parse_datetime(valor)
    else:
        return None
    if fecha is not None and timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha, timezone.get_current_timezone())
    return fecha


def _es_de_fondo(request: HttpRequest) -> bool:
    """¿La petición espera datos y no una página entera?"""
    pedido = request.headers.get("x-requested-with", "")
    acepta = request.headers.get("accept", "")
    return pedido == "XMLHttpRequest" or "application/json" in acepta


def _contexto(request: HttpRequest) -> dict:
    return {"limite": minutos_de_bloqueo(), "siguiente": request.get_full_path()}


class BloqueoPorInactividad:
    """Bloquea la sesión cuando pasa demasiado tiempo sin usarla.

    Va después de ``AuthenticationMiddleware``: hasta que no se sabe quién es el
    usuario no hay nada que bloquear. Las peticiones de fondo (AJAX y ``fetch``)
    reciben un 423 en vez de la pantalla, para que el JavaScript pueda enseñarla
    sin recargar.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        limite = minutos_de_bloqueo()
        usuario = getattr(request, "user", None)

        if not limite or usuario is None or not usuario.is_authenticated or _exenta(request.path):
            return self.get_response(request)

        ahora = timezone.now()
        if self._esta_bloqueada(request, ahora, limite):
            request.session[BLOQUEADA] = True
            if _es_de_fondo(request):
                return JsonResponse({"bloqueada": True, "minutos": limite}, status=423)
            return render(request, "bloqueado.html", _contexto(request), status=423)

        request.session[ULTIMA] = ahora.isoformat()
        return self.get_response(request)

    @staticmethod
    def _esta_bloqueada(request: HttpRequest, ahora: datetime, limite: int) -> bool:
        if request.session.get(BLOQUEADA):
            return True
        ultima = _marca(request.session.get(ULTIMA))
        if ultima is None:
            return False
        return (ahora - ultima).total_seconds() > limite * 60


# --------------------------------------------------------------- las acciones


@login_required
@require_POST
def bloquear(request: HttpRequest) -> HttpResponse:
    """Bloquea la pantalla a mano (el botón «Bloquear» de la barra).

    Devuelve la pantalla de bloqueo sin redirigir: así el formulario lleva en
    ``next`` la página en la que estaba y al desbloquear se vuelve a ella.
    """
    request.session[BLOQUEADA] = True
    if _es_de_fondo(request):
        return JsonResponse({"bloqueada": True})
    siguiente = request.POST.get("next") or reverse("facturacion:facturas")
    return render(
        request,
        "bloqueado.html",
        {"limite": minutos_de_bloqueo(), "siguiente": siguiente},
        status=423,
    )


@login_required
def bloquear_pantalla(request: HttpRequest) -> HttpResponse:
    """La pantalla de bloqueo, pedida a mano. Si no hay bloqueo, no hay pantalla."""
    if not request.session.get(BLOQUEADA):
        return redirect("facturacion:facturas")
    return render(request, "bloqueado.html", _contexto(request), status=423)


@login_required
@require_POST
def desbloquear(request: HttpRequest) -> HttpResponse:
    """Quita el bloqueo si la clave es la del usuario que tenía la sesión."""
    clave = request.POST.get("password") or ""
    de_fondo = _es_de_fondo(request)

    if not clave:
        return _error(request, "Escriba su clave.", de_fondo)

    usuario = authenticate(request, username=request.user.get_username(), password=clave)
    if usuario is None or usuario.pk != request.user.pk:
        return _error(request, "Esa no es su clave.", de_fondo)

    request.session[BLOQUEADA] = False
    request.session[ULTIMA] = timezone.now().isoformat()

    destino = request.POST.get("next") or reverse("facturacion:facturas")
    if de_fondo:
        return JsonResponse({"ok": True, "siguiente": destino})
    return redirect(destino)


def _error(request: HttpRequest, mensaje: str, de_fondo: bool) -> HttpResponse:
    if de_fondo:
        return JsonResponse({"ok": False, "error": mensaje}, status=400)
    contexto = _contexto(request) | {"error": mensaje}
    return render(request, "bloqueado.html", contexto, status=400)
