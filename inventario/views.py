"""Las pantallas del inventario: lo que hay, y su libro de movimientos."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from factec.django.documentos import Producto, TipoProducto

from facturero.marco import marco
from personalize_options.decoradores import (
    exigir_escritura,
    requiere_escritura,
    requiere_lectura,
)

from .forms import FormularioMovimiento
from .models import Existencia, Movimiento, TipoMovimiento

__all__ = ["inventario", "kardex", "movimiento_nuevo", "movimiento_anular"]


@login_required
@requiere_lectura("inventario")
def inventario(request: HttpRequest) -> HttpResponse:
    """Lo que hay de cada bien, con el valor y los avisos de reposición.

    Se listan todos los bienes, tengan existencia o no: un producto que nunca se
    contó aparece con cero, que es justo lo que hay que ver.
    """
    bienes = (
        Producto.objects.filter(tipo=TipoProducto.PRODUCTO.value)
        .select_related("existencia")
        .order_by("descripcion")
    )

    texto = (request.GET.get("q") or "").strip()
    solo_bajo = request.GET.get("bajo") or ""
    if texto:
        bienes = bienes.filter(
            Q(descripcion__icontains=texto) | Q(codigo_principal__icontains=texto)
        )

    filas = []
    for producto in bienes:
        existencia = getattr(producto, "existencia", None) or Existencia(producto=producto)
        filas.append({"producto": producto, "existencia": existencia})
    bajo_minimo = [fila for fila in filas if fila["existencia"].bajo_minimo]
    if solo_bajo:
        filas = bajo_minimo

    contexto = {
        **marco(request),
        "filas": filas,
        "filtros": {"q": texto, "bajo": solo_bajo},
        "cuantos": len(filas),
        "bajo_minimo": len(bajo_minimo),
        "valor_total": sum((fila["existencia"].valor for fila in filas), Decimal("0")),
        "ultimos": Movimiento.objects.select_related("producto", "usuario")[:8],
    }
    return render(request, "inventario/inventario.html", contexto)


@login_required
@requiere_lectura("inventario")
def kardex(request: HttpRequest, pk: int) -> HttpResponse:
    """El libro de un producto: cada movimiento con el saldo que va quedando."""
    producto = get_object_or_404(Producto, pk=pk)
    movimientos = list(producto.movimientos.select_related("usuario").order_by("fecha", "pk"))

    # El saldo se calcula hacia adelante, para que se lea como un extracto.
    acumulado = Decimal("0")
    filas = []
    for movimiento in movimientos:
        acumulado += movimiento.delta()
        filas.append({"movimiento": movimiento, "saldo": acumulado})
    filas.reverse()

    existencia = getattr(producto, "existencia", None) or Existencia(producto=producto)
    contexto = {
        **marco(request),
        "producto": producto,
        "existencia": existencia,
        "filas": filas,
        "formulario": FormularioMovimiento(producto=producto),
        "tipos": TipoMovimiento,
    }
    return render(request, "inventario/kardex.html", contexto)


@login_required
@require_POST
@requiere_escritura("inventario")
def movimiento_nuevo(request: HttpRequest, pk: int) -> HttpResponse:
    """Registra una entrada, una salida o un ajuste."""
    producto = get_object_or_404(Producto, pk=pk)
    formulario = FormularioMovimiento(request.POST, producto=producto)
    if formulario.is_valid():
        movimiento = formulario.save(commit=False)
        movimiento.producto = producto
        movimiento.usuario = request.user
        movimiento.save()
        messages.success(
            request,
            f"{movimiento.get_tipo_display()} de {movimiento.cantidad} {producto.unidad_medida or ''} "
            f"registrada. Quedan {getattr(producto.existencia, 'cantidad', 0)}.",
        )
    else:
        for errores in formulario.errors.values():
            for texto in errores:
                messages.error(request, texto)
    return redirect("inventario:kardex", pk=producto.pk)


@login_required
@require_POST
@requiere_escritura("inventario")
def movimiento_anular(request: HttpRequest, pk: int) -> HttpResponse:
    """Anula un movimiento: la cantidad vuelve a su sitio."""
    movimiento = get_object_or_404(Movimiento.objects.select_related("producto"), pk=pk)
    producto = movimiento.producto
    if movimiento.tipo == TipoMovimiento.FACTURA.value:
        messages.error(
            request,
            "Ese movimiento lo puso una factura al emitirse. Para corregirlo, anule la "
            "factura con una nota de crédito y registre el movimiento a mano.",
        )
        return redirect("inventario:kardex", pk=producto.pk)

    movimiento.delete()
    messages.success(request, "Movimiento anulado y cantidad devuelta a la existencia.")
    return redirect("inventario:kardex", pk=producto.pk)
