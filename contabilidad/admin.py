"""El admin de la contabilidad: para revisar, no para el día a día."""

from __future__ import annotations

from django.contrib import admin

from .models import (
    Asiento,
    Compra,
    ConfiguracionContable,
    Cuenta,
    Empleado,
    LineaAsiento,
    PeriodoContable,
)


class LineaInline(admin.TabularInline):
    model = LineaAsiento
    extra = 0
    autocomplete_fields = ["cuenta", "tercero"]


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "tipo", "naturaleza", "nivel", "permite_movimientos", "activa"]
    list_filter = ["tipo", "naturaleza", "activa", "permite_movimientos"]
    search_fields = ["codigo", "nombre"]
    ordering = ["codigo"]


@admin.register(PeriodoContable)
class PeriodoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "ejercicio", "mes", "fecha_inicio", "fecha_fin", "estado"]
    list_filter = ["estado", "ejercicio"]
    search_fields = ["nombre"]


@admin.register(Asiento)
class AsientoAdmin(admin.ModelAdmin):
    list_display = ["numero", "fecha", "concepto", "tipo", "estado", "periodo"]
    list_filter = ["estado", "tipo", "periodo__ejercicio"]
    search_fields = ["numero", "concepto", "referencia"]
    date_hierarchy = "fecha"
    inlines = [LineaInline]
    autocomplete_fields = ["comprobante"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("periodo")


@admin.register(LineaAsiento)
class LineaAdmin(admin.ModelAdmin):
    list_display = ["asiento", "cuenta", "descripcion", "debe", "haber"]
    list_filter = ["cuenta__tipo"]
    search_fields = ["descripcion", "documento"]
    autocomplete_fields = ["asiento", "cuenta", "tercero"]


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ["fecha", "proveedor", "tipo_comprobante", "numero", "total", "asiento"]
    list_filter = ["tipo_comprobante", "fecha"]
    search_fields = ["numero", "proveedor__razon_social", "concepto"]
    date_hierarchy = "fecha"
    autocomplete_fields = ["proveedor", "cuenta", "retencion", "asiento"]


@admin.register(ConfiguracionContable)
class ConfiguracionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activa", "tipo_empleador", "ente_seg_social"]
    list_filter = ["activa"]


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ["anio", "apellidos", "nombres", "identificacion", "suel_sal", "val_ret", "activo"]
    list_filter = ["anio", "activo", "tipo_identificacion"]
    search_fields = ["apellidos", "nombres", "identificacion"]
