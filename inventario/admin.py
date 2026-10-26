"""El inventario también en el admin, para lo que se haga de vez en cuando."""

from __future__ import annotations

from django.contrib import admin

from .models import Existencia, Movimiento

__all__ = ["ExistenciaAdmin", "MovimientoAdmin"]


@admin.register(Existencia)
class ExistenciaAdmin(admin.ModelAdmin):
    list_display = ("producto", "cantidad", "minimo", "ubicacion", "actualizado")
    list_filter = ("ubicacion",)
    search_fields = ("producto__descripcion", "producto__codigo_principal")
    autocomplete_fields = ("producto",)


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "producto", "tipo", "cantidad", "referencia", "usuario")
    list_filter = ("tipo", "fecha")
    search_fields = ("producto__descripcion", "producto__codigo_principal", "motivo", "referencia")
    date_hierarchy = "fecha"
    autocomplete_fields = ("producto",)
