"""Filtros para pintar los estados con los chips de Metro."""

from __future__ import annotations

from django import template

from facturacion import chips

register = template.Library()


@register.filter(name="chip")
def chip(valor: object) -> str:
    """Clases del chip de Metro para un estado («success soft», «alert»…)."""
    return chips.chip(valor)


@register.filter(name="en_marcha")
def en_marcha(valor: object) -> bool:
    """¿El comprobante está en manos del SRI ahora mismo?"""
    return chips.en_marcha(valor)


@register.filter(name="avance")
def avance(valor: object) -> int:
    """Cuánto ha avanzado el comprobante (0 a 100)."""
    return chips.avance(valor)


@register.filter(name="clase_avance")
def clase_avance(valor: object) -> str:
    """El color de la barra del ciclo («exito», «cuidado», «peligro»)."""
    return chips.clase_avance(valor)


@register.filter(name="nombre_estado")
def nombre_estado(valor: object) -> str:
    """El nombre largo del estado («AUTORIZADO» → «Autorizado»)."""
    return chips.nombre(valor)
