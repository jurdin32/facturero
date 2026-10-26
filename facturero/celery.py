"""Aplicación de Celery del proyecto.

Con ``autodiscover_tasks()`` se registran solas las tareas del paquete
(``factec.django.tasks``), así que el worker reconoce:

* ``sri_fe.emitir_comprobante``      → firma, envía y espera la autorización
* ``sri_fe.consultar_autorizacion``  → consulta el estado de un comprobante recibido
* ``sri_fe.reintentar_pendientes``   → recupera los que quedaron a medias
* ``sri_fe.revisar_certificado``     → revisa la firma electrónica y avisa

Arranque de los servicios::

    celery -A facturero worker -l info       # obligatorio para emitir en 2.º plano
    celery -A facturero beat -l info         # opcional: tareas periódicas
"""

import os

# En macOS y Windows el pool de procesos usa «spawn» (no «fork») y, sin esta
# variable, Celery no prepara el registro de tareas en los procesos hijos: la
# tarea entra al worker y falla con «ValueError: not enough values to unpack».
# Con ella, cada hijo prepara las tareas como si el pool hubiera hecho execv.
os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")

from celery import Celery  # noqa: E402  (después de la variable, a propósito)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "facturero.settings")

app = Celery("facturero")

# Toda la configuración de Celery se lee de settings.py con el prefijo CELERY_:
# CELERY_BROKER_URL, CELERY_BEAT_SCHEDULE, CELERY_TIMEZONE…
app.config_from_object("django.conf:settings", namespace="CELERY")

# Encuentra las tareas de las apps instaladas, incluida factec.django.
app.autodiscover_tasks()
