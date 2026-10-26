"""Administración de las cajas: para revisar un cierre, no para el día a día."""

from __future__ import annotations

from django.contrib import admin

from .models import MovimientoCaja, SesionCaja


class MovimientoCajaInline(admin.TabularInline):
    model = MovimientoCaja
    extra = 0
    readonly_fields = ("usuario", "fecha", "comprobante")


@admin.register(SesionCaja)
class SesionCajaAdmin(admin.ModelAdmin):
    list_display = (
        "usuario",
        "estado",
        "saldo_inicial",
        "abierta_en",
        "cerrada_en",
        "saldo_declarado",
    )
    list_filter = ("estado", "usuario")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name")
    inlines = [MovimientoCajaInline]


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "sesion", "tipo", "concepto", "importe", "usuario")
    list_filter = ("tipo", "usuario")
    search_fields = ("concepto", "referencia", "sesion__usuario__username")
