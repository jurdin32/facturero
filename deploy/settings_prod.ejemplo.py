"""Ajustes de producción: el archivo que vive en el servidor, no en el repositorio.

Se copia en el servidor como ``facturero/settings_prod.py`` y los servicios —la web
y los tres de Celery— arrancan con ``DJANGO_SETTINGS_MODULE=facturero.settings_prod``.
Así el mismo código sirve en local (``facturero.settings``, con DEBUG y SQLite) y en
el servidor, sin archivos ``.env``.

Lo que cambia respecto de ``settings.py``:

* ``DEBUG`` apagado: sin él, cualquier error enseña el código y la configuración.
* Su propia ``SECRET_KEY``, larga y aleatoria, distinta de la de desarrollo.
* ``ALLOWED_HOSTS`` con el dominio de verdad y los orígenes de confianza.
* Cookies solo por HTTPS y la redirección a HTTPS.
* PostgreSQL en vez de SQLite.

Para generar la clave::

    python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
"""

from .settings import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = "PONGA-AQUI-UNA-CLAVE-LARGA-Y-ALEATORIA"

ALLOWED_HOSTS = ["facturacion.sudominio.com"]

# El dominio público, para el CSRF de la tienda y del admin.
CSRF_TRUSTED_ORIGINS = ["https://facturacion.sudominio.com"]

# Todo por HTTPS.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "factiz",
        "USER": "factiz",
        "PASSWORD": "PONGA-AQUI-LA-CLAVE-DE-POSTGRESQL",
        "HOST": "127.0.0.1",
        "PORT": "5432",
        # Las transacciones se confirman al terminar la vista: si algo falla a
        # mitad, no queda medio comprobante guardado.
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": 60,
    }
}

# Los archivos subidos (el logo y las fotos de la tienda) y los estáticos, tal
# como los sirve el servidor web.
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405

# Los errores no se enseñan al usuario, pero no se pierden: quedan en el registro
# del servicio (journalctl -u facturero).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "sencillo": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "sencillo"},
    },
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["consola"], "level": "ERROR", "propagate": False},
    },
}
