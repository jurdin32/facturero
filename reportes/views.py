"""Las pantallas de los reportes: el índice, cada reporte y el manual.

Un reporte se pide con su clave en la dirección y el período en la query. La misma
dirección sirve las tres salidas: sin ``formato`` se ve en el navegador, con
``formato=pdf`` se abre el PDF y con ``formato=xlsx`` se descarga el Excel. Así el
botón de cada salida es el mismo enlace con otro parámetro, y el período elegido no
se pierde al cambiar de salida.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from personalize_options.decoradores import requiere_lectura
from personalize_options.permisos import de_la_peticion

from conta_ec.django.models import Cuenta
from factec.django import conf

from facturero.marco import marco

from . import catalogo, manual, salidas
from .periodos import PERIODOS, Filtro, resolver
from .tabla import Tabla

__all__ = ["indice", "manual_del_sistema", "reporte"]


def _emisor() -> tuple[str, str]:
    """La razón social y el RUC del emisor activo, para el encabezado."""
    configuracion = conf.configuracion_activa()
    if configuracion is None:
        return "", ""
    return configuracion.razon_social or "", configuracion.ruc or ""


def _la_cuenta(request: HttpRequest) -> Any:
    """La cuenta del libro mayor, si el reporte la pide."""
    try:
        numero = int(request.GET.get("cuenta") or 0)
    except ValueError:
        numero = 0
    if not numero:
        return None
    return Cuenta.objects.filter(pk=numero).first()


def _clave_de_permiso(clave: str) -> str:
    """La opción que gobierna un reporte suelto (``reporte_ventas``)."""
    return f"reporte_{clave}"


@login_required
@requiere_lectura("reportes")
def indice(request: HttpRequest) -> HttpResponse:
    """Todos los reportes, por apartado, con lo que trae cada uno."""
    permisos = de_la_peticion(request)
    grupos = [
        (grupo, [reporte for reporte in reportes if permisos.puede_leer(_clave_de_permiso(reporte.clave))])
        for grupo, reportes in catalogo.por_grupo()
    ]
    return render(
        request,
        "reportes/indice.html",
        {
            **marco(request),
            "grupos": [(grupo, reportes) for grupo, reportes in grupos if reportes],
            "cuantos": sum(len(reportes) for _grupo, reportes in grupos),
            "periodos": PERIODOS,
            "filtro": resolver(request.GET),
        },
    )


@login_required
@requiere_lectura("reportes")
def reporte(request: HttpRequest, clave: str) -> HttpResponse:
    """Un reporte, en la pantalla o en el archivo que se pida."""
    definicion = catalogo.de(clave)
    if definicion is None:
        raise Http404(f"No hay un reporte llamado «{clave}».")

    permisos = de_la_peticion(request)
    if not permisos.puede_leer(_clave_de_permiso(clave)):
        raise PermissionDenied(f"No tiene permiso para el reporte «{definicion.nombre}».")

    cuenta = _la_cuenta(request) if definicion.pide_cuenta else None
    filtro = resolver(request.GET, cuenta=cuenta.pk if cuenta else None)
    tabla = catalogo.construir(definicion, filtro, cuenta=cuenta)

    empresa, ruc = _emisor()
    ficha = salidas.Ficha(
        empresa=empresa,
        ruc=ruc,
        titulo=tabla.titulo,
        subtitulo=tabla.subtitulo,
        periodo=filtro.etiqueta,
        usuario=request.user.get_username(),
        generado=datetime.now(),
        resumen=tabla.resumen,
        notas=tabla.notas,
        archivo=definicion.clave,
    )

    formato = (request.GET.get("formato") or "html").lower()
    if formato in ("pdf", "xlsx"):
        return _archivo(tabla, ficha, formato, descargar=bool(request.GET.get("descargar")))

    return render(
        request,
        "reportes/reporte.html",
        {
            **marco(request),
            "definicion": definicion,
            "tabla": tabla,
            "renglones": tabla.renglones(),
            "totales": tabla.renglon_de_totales(),
            "filtro": filtro,
            "periodos": PERIODOS,
            "cuentas": Cuenta.objects.order_by("codigo") if definicion.pide_cuenta else [],
            "ficha": ficha,
        },
    )


def _archivo(tabla: Tabla, ficha: salidas.Ficha, formato: str, descargar: bool) -> HttpResponse:
    """El PDF o el Excel del reporte, listo para el navegador."""
    if formato == "pdf":
        contenido = salidas.pdf(tabla, ficha)
        tipo = "application/pdf"
    else:
        contenido = salidas.excel(tabla, ficha)
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    respuesta = HttpResponse(contenido, content_type=tipo)
    nombre = salidas.nombre_de_archivo(ficha, tabla, formato)
    como = "attachment" if descargar or formato == "xlsx" else "inline"
    respuesta["Content-Disposition"] = f'{como}; filename="{nombre}"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@login_required
def manual_del_sistema(request: HttpRequest) -> HttpResponse:
    """El manual de uso, con las capturas de cada pantalla."""
    return render(
        request,
        "reportes/manual.html",
        {
            **marco(request),
            "secciones": manual.secciones(),
            "indice": manual.INDICE,
            "mapa": manual.mapa_de_opciones(),
        },
    )
