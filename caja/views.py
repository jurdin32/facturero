"""La pantalla de caja: abrir el turno, mover efectivo y cerrarlo."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from personalize_options.decoradores import exigir_escritura, requiere_lectura

from facturero.marco import marco

from . import servicios
from .acta import acta as acta_pdf
from .forms import AbrirCajaForm, CerrarCajaForm, MovimientoCajaForm
from .models import MovimientoCaja, SesionCaja

__all__ = ["acta", "tablero"]


def _movimientos(sesion: SesionCaja | None, request: HttpRequest):
    if sesion is None:
        return MovimientoCaja.objects.none()
    lista = sesion.movimientos.select_related("usuario", "comprobante")
    texto = (request.GET.get("q") or "").strip()
    tipo = request.GET.get("tipo") or ""
    if texto:
        lista = lista.filter(
            Q(concepto__icontains=texto) | Q(referencia__icontains=texto)
        )
    if tipo in {MovimientoCaja.Tipo.INGRESO.value, MovimientoCaja.Tipo.EGRESO.value}:
        lista = lista.filter(tipo=tipo)
    return lista.order_by("-fecha", "-pk")


@login_required
@requiere_lectura("caja")
def tablero(request: HttpRequest) -> HttpResponse:
    sesion = servicios.sesion_abierta(request.user)
    formulario_abrir = AbrirCajaForm()
    formulario_movimiento = MovimientoCajaForm(initial={"tipo": MovimientoCaja.Tipo.INGRESO.value})
    formulario_cerrar = CerrarCajaForm()

    if request.method == "POST":
        exigir_escritura(request, "caja")
        accion = request.POST.get("accion") or ""
        try:
            if accion == "abrir":
                formulario_abrir = AbrirCajaForm(request.POST)
                if formulario_abrir.is_valid():
                    servicios.abrir(
                        request.user,
                        formulario_abrir.cleaned_data.get("saldo_inicial") or 0,
                        formulario_abrir.cleaned_data.get("observaciones") or "",
                    )
                    messages.success(request, "Caja abierta. Ya puede registrar movimientos.")
                    return redirect("caja:tablero")
                messages.error(request, "Revise el saldo inicial.")

            elif accion == "movimiento":
                formulario_movimiento = MovimientoCajaForm(request.POST)
                if sesion is None:
                    messages.error(request, "Primero abra su caja.")
                elif formulario_movimiento.is_valid():
                    datos = formulario_movimiento.cleaned_data
                    servicios.registrar_movimiento(
                        sesion,
                        request.user,
                        tipo=datos["tipo"],
                        concepto=datos["concepto"],
                        importe=datos["importe"],
                        referencia=datos.get("referencia") or "",
                    )
                    messages.success(request, "Movimiento registrado en la caja.")
                    return redirect("caja:tablero")
                else:
                    messages.error(request, "Revise los datos del movimiento.")

            elif accion == "cerrar":
                formulario_cerrar = CerrarCajaForm(request.POST)
                if sesion is None:
                    messages.error(request, "No hay una caja abierta.")
                elif formulario_cerrar.is_valid():
                    datos = formulario_cerrar.cleaned_data
                    cerrada = servicios.cerrar(
                        sesion,
                        datos["saldo_declarado"],
                        datos.get("observaciones_cierre") or "",
                        desglose=formulario_cerrar.desglose(),
                    )
                    if cerrada.diferencia:
                        diferencia = f"{cerrada.diferencia:.2f}".replace(".", ",")
                        messages.warning(
                            request,
                            f"Caja cerrada con una diferencia de {diferencia}. "
                            "Quedó registrada para revisión.",
                        )
                    else:
                        messages.success(request, "Caja cerrada y cuadrada.")
                    return redirect("caja:tablero")
                else:
                    messages.error(request, "Escriba el efectivo contado para cerrar.")
            else:
                messages.error(request, "No se reconoció la acción.")
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)

    sesion = servicios.sesion_abierta(request.user)
    ultima_cerrada = (
        SesionCaja.objects.filter(
            usuario=request.user, estado=SesionCaja.Estado.CERRADA.value
        )
        .order_by("-cerrada_en")
        .first()
    )
    historial = (
        SesionCaja.objects.filter(
            usuario=request.user, estado=SesionCaja.Estado.CERRADA.value
        )
        .order_by("-cerrada_en")[:8]
    )
    contexto: dict[str, Any] = {
        **marco(request),
        "sesion": sesion,
        "movimientos": _movimientos(sesion, request),
        "filtros": {"q": (request.GET.get("q") or "").strip(), "tipo": request.GET.get("tipo") or ""},
        "formulario_abrir": formulario_abrir,
        "formulario_movimiento": formulario_movimiento,
        "formulario_cerrar": formulario_cerrar,
        "ultima_cerrada": ultima_cerrada,
        "historial": historial,
    }
    return render(request, "caja/tablero.html", contexto)


@login_required
@requiere_lectura("caja")
def acta(request: HttpRequest, pk: int) -> HttpResponse:
    """El acta de cierre de una sesión, en PDF.

    Se puede bajar cualquier sesión cerrada, propia o de otro usuario: el acta es el
    respaldo del arqueo y lo revisa quien lleva la contabilidad.
    """
    from django.utils import timezone

    sesion = get_object_or_404(
        SesionCaja.objects.select_related("usuario"), pk=pk
    )
    if sesion.abierta:
        messages.warning(
            request, "Esta caja está abierta: el acta se genera al cerrarla."
        )
        return redirect("caja:tablero")

    contenido = acta_pdf(sesion, sesion.movimientos.select_related("usuario"))
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    nombre = (
        f"acta-caja-{sesion.usuario.get_username()}-"
        f"{(sesion.cerrada_en or sesion.abierta_en):%Y%m%d}.pdf"
    )
    respuesta["Content-Disposition"] = f'inline; filename="{nombre}"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta
