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
from factec.django.conf import planificador  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "facturero.settings")

app = Celery("facturero")

# La configuración de Celery vive aquí, no en settings.py: es cosa del worker, no
# del proyecto. El broker se puede cambiar con la variable de entorno
# CELERY_BROKER_URL; el resto son los valores con los que se probó.
app.conf.update(
    broker_url=os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0"),
    timezone="America/Guayaquil",
    enable_utc=True,
    # Los eventos alimentan el panel de Flower sin arrancar el worker con «-E».
    worker_send_task_events=True,
    task_send_sent_event=True,
    # Las tareas periódicas del paquete: revisa la firma a las 7:00 y reintenta
    # cada 10 minutos los comprobantes que quedaron a medias.
    beat_schedule={**planificador()},
)

# Encuentra las tareas de las apps instaladas, incluida factec.django.
app.autodiscover_tasks()
