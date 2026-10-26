"""Proyecto facturero: facturación electrónica del SRI con el paquete factec.

Aquí se carga la app de Celery para que ``celery -A facturero`` la encuentre.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
