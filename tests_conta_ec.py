"""Las pruebas del paquete ``conta_ec``, con las del proyecto.

Las pruebas viven en el paquete (``conta_ec.django.tests``), pero el proyecto las
corre junto con las suyas: `manage.py test` descubre desde la carpeta del proyecto,
y el paquete está instalado aparte. Este módulo es el puente.
"""

from conta_ec.django.tests import *  # noqa: F401,F403
