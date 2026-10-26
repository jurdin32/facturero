"""La pantalla de caja: abrir el turno, mover efectivo y cerrarlo."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from personalize_options import permisos
from personalize_options.decoradores import exigir_escritura, requiere_lectura

from facturero.marco import marco

from . import servicios
from .acta import acta as acta_pdf
from .forms import AbrirCajaForm, CerrarCajaForm, MovimientoCajaForm, ValeCajaForm
from .models import MovimientoCaja, SesionCaja

__all__ = ["acta", "revision", "tablero", "vale_nuevo", "vale_pdf", "vales"]


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
def acta(request: HttpRequest, pk: int) -> HttpResponse:
    """El acta de cierre de una sesión, en PDF.

    Se puede bajar cualquier sesión cerrada, propia o de otro usuario: el acta es el
    respaldo del arqueo y la mira quien lleva la contabilidad. La baja el dueño de
    la caja —con su permiso— o quien revisa los cuadres, que necesita leerla para
    aprobarlos; por eso aquí no basta un solo permiso.
    """
    quien = permisos.de_la_peticion(request)
    if not (quien.puede_leer("caja") or quien.puede_leer("revision_caja")):
        raise PermissionDenied("No tiene permiso para ver el acta de caja.")

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


# ------------------------------------------------- la revisión de los cuadres


@login_required
@requiere_lectura("revision_caja")
def revision(request: HttpRequest) -> HttpResponse:
    """Los cuadres de caja cerrados, para revisarlos y aprobarlos uno por uno.

    Enseña lo que hay que mirar —esperado, contado, diferencia y el desglose— y deja
    aprobar el cuadre o dejarlo observado con su nota. Los faltantes se pueden cobrar
    con un vale desde la misma fila.
    """
    from .models import ValeCaja

    estado = request.GET.get("revision") or ""
    cerradas = SesionCaja.objects.filter(estado=SesionCaja.Estado.CERRADA.value)
    if estado in {"sin_revisar", "aprobada", "observada"}:
        cerradas = cerradas.filter(revision=estado)
    cerradas = cerradas.select_related("usuario", "revisada_por").order_by("-cerrada_en")

    if request.method == "POST":
        exigir_escritura(request, "revision_caja")
        sesion = get_object_or_404(SesionCaja, pk=request.POST.get("sesion") or 0)
        decision = request.POST.get("decision") or ""
        nota = request.POST.get("nota") or ""
        try:
            servicios.revisar(sesion, request.user, decision, nota)
            messages.success(
                request,
                f"El cuadre del {sesion.cerrada_en:%d/%m/%Y} quedó "
                f"{sesion.get_revision_display().lower()}.",
            )
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
        return redirect("supervision:cuadres")

    def _cuadre(sesion: SesionCaja) -> dict[str, Any]:
        """Lo que la ficha necesita: el faltante y cuánto queda por cobrar de él."""
        faltante = -sesion.diferencia if sesion.diferencia < 0 else Decimal("0")
        vales = list(sesion.vales.exclude(estado=ValeCaja.Estado.ANULADO.value))
        cubierto = sum((vale.importe for vale in vales), Decimal("0"))
        return {
            "sesion": sesion,
            "faltante": faltante or None,
            "vales": vales,
            "por_cobrar": (faltante - cubierto) if faltante > cubierto else None,
        }

    cuadres = [_cuadre(sesion) for sesion in cerradas[:60]]
    pendientes = [
        _cuadre(sesion) for sesion in cerradas if sesion.revision == "sin_revisar"
    ]
    return render(
        request,
        "caja/revision.html",
        {
            **marco(request),
            "cuadres": cuadres,
            "filtros": {"revision": estado},
            "cuantos": len(cuadres),
            "por_revisar": len(pendientes),
            "con_faltante": sum(1 for fila in pendientes if fila["faltante"]),
        },
    )


# ------------------------------------------------------------ los vales


@login_required
@requiere_lectura("vales_caja")
def vales(request: HttpRequest) -> HttpResponse:
    """Los vales de caja: lo que está pendiente de cobrar y lo que ya se cobró."""
    from .models import ValeCaja

    estado = request.GET.get("estado") or ""
    lista = ValeCaja.objects.select_related("responsable", "sesion", "creado_por")
    if estado in ValeCaja.Estado.values:
        lista = lista.filter(estado=estado)

    if request.method == "POST":
        exigir_escritura(request, "vales_caja")
        vale = get_object_or_404(ValeCaja, pk=request.POST.get("vale") or 0)
        que = request.POST.get("que") or ""
        try:
            if que == "cobrar":
                servicios.cobrar_vale(vale, request.POST.get("nota") or "")
                messages.success(request, f"El vale {vale.numero} quedó cobrado.")
            elif que == "anular":
                servicios.anular_vale(vale, request.POST.get("nota") or "")
                messages.warning(request, f"El vale {vale.numero} quedó anulado.")
            else:
                messages.error(request, "No se reconoció la acción.")
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
        return redirect("supervision:vales")

    pendientes = lista.filter(estado=ValeCaja.Estado.PENDIENTE.value)
    return render(
        request,
        "caja/vales.html",
        {
            **marco(request),
            "vales": lista[:80],
            "filtros": {"estado": estado},
            "estados": ValeCaja.Estado.choices,
            "pendiente_total": sum((vale.importe for vale in pendientes), Decimal("0")),
            "cuantos_pendientes": pendientes.count(),
        },
    )


@login_required
@requiere_lectura("vales_caja")
def vale_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """El vale en PDF, para imprimirlo y firmarlo."""
    from .models import ValeCaja
    from .vale import vale as vale_pdf_bytes

    el_vale = get_object_or_404(
        ValeCaja.objects.select_related("responsable", "sesion", "creado_por"), pk=pk
    )
    respuesta = HttpResponse(vale_pdf_bytes(el_vale), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'inline; filename="vale-{el_vale.numero}.pdf"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@login_required
@requiere_lectura("vales_caja")
def vale_nuevo(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Hacer un vale: sobre un turno con faltante o suelto (anticipo, gasto)."""
    sesion = get_object_or_404(SesionCaja, pk=pk) if pk else None
    if request.method == "POST":
        exigir_escritura(request, "vales_caja")
        formulario = ValeCajaForm(request.POST, sesion=sesion)
        if formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                vale = servicios.crear_vale(
                    responsable=datos["responsable"],
                    importe=datos["importe"],
                    motivo=datos["motivo"],
                    tipo=datos["tipo"],
                    sesion=sesion,
                    creado_por=request.user,
                    nota=datos.get("nota") or "",
                )
            except ValidationError as error:
                for mensaje in error.messages:
                    messages.error(request, mensaje)
            else:
                messages.success(
                    request,
                    f"Vale {vale.numero} creado, pendiente de cobro. "
                    "Ábralo con «Imprimir» para firmarlo.",
                )
                return redirect("supervision:vales")
        else:
            messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = ValeCajaForm(sesion=sesion)

    return render(
        request,
        "caja/vale_nuevo.html",
        {**marco(request), "formulario": formulario, "sesion": sesion},
    )
