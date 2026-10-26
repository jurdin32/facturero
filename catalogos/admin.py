"""La tabla de retenciones, también en el admin, para consultarla de vez en cuando.

No se da de alta a mano: la carga el comando ``cargar_codigos_retencion`` desde el
archivo del SRI. Aquí solo se mira y, si acaso, se corrige un concepto.
"""

from __future__ import annotations

from django.contrib import admin

from .models import CodigoRetencion

__all__ = ["CodigoRetencionAdmin"]


@admin.register(CodigoRetencion)
class CodigoRetencionAdmin(admin.ModelAdmin):
    list_display = ("codigo", "impuesto", "como_porcentaje", "concepto")
    list_filter = ("impuesto",)
    search_fields = ("codigo", "concepto")
    ordering = ("impuesto", "orden", "codigo")
    list_per_page = 50
