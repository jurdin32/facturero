"""Configuración de Django del proyecto.

Aquí sólo va lo que es de **Django**: las aplicaciones, el middleware, las
plantillas, la base de datos, los estáticos, la zona horaria y las direcciones de
entrada y salida.

Todo lo que se puede cambiar sin tocar código —el modo de los permisos, el
bloqueo de la pantalla, el ambiente del SRI, si se descuenta el inventario o si se
contabiliza al autorizar— vive en la **base de datos**, en la tabla de ajustes:

* cada paquete y cada aplicación declara los suyos en su ``AppConfig.ready()``
  (ver ``personalize_options.ajustes``);
* al terminar ``migrate`` quedan sembrados con su valor de serie;
* se cambian desde el admin (Seguridad → Ajustes) y valen al momento.

El único secreto fuera de la base es la clave de cifrado del certificado, que
puede venir en la variable de entorno ``SRI_CLAVE_CIFRADO``.
"""
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-bl#nky+tb!xofqm2-_+b@e$yb=w6$$56e__*ttf=md0i@%qe-i'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*', 'localhost', '127.0.0.1']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'factec.django',
    # Aplicaciones del proyecto, una por tema.
    'facturacion',
    # Los demás comprobantes electrónicos: nota de crédito, nota de débito,
    # liquidación de compra, guía de remisión y comprobante de retención.
    'comprobantes',
    'catalogos',
    'inventario',
    # El plan de cuentas, los asientos, los estados financieros y los anexos del SRI.
    'contabilidad',
    # Apertura, movimientos y cierre de caja por usuario.
    'caja',
    'configuracion',
    # Las pantallas de la seguridad: roles, permisos y quién los lleva.
    'seguridad',
    # Los reportes y las estadísticas, con sus salidas en PDF y Excel, y el manual.
    'reportes',
    # Roles y permisos de lectura/escritura por opción. Es un paquete externo, como
    # factec (pip install -e ../personalize_options), y trae sus propias migraciones:
    # basta con ponerlo aquí y migrar.
    'personalize_options',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Deja los permisos del usuario en `request.permisos` (ver personalize_options/).
    'personalize_options.middleware.PermisosMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Bloquea la pantalla tras un rato sin usar la aplicación (ver facturero/sesion.py).
    'facturero.sesion.BloqueoPorInactividad',
]

ROOT_URLCONF = 'facturero.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Una sola carpeta de plantillas para todo el proyecto (sin carpetas por app).
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # La fecha de nuestro CSS y nuestro JavaScript, para que el navegador
                # no siga sirviendo la versión vieja después de cambiarlos.
                'facturero.estaticos.sello_estatico',
            ],
        },
    },
]

WSGI_APPLICATION = 'facturero.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'es-ec'

TIME_ZONE = 'America/Guayaquil'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'

# Una sola carpeta de estáticos y CSS/JS escritos a mano: sin compilación ni CDN.
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Archivos subidos: el logo del emisor y el certificado .p12 del SRI.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Entrar y salir de la interfaz
LOGIN_URL = 'entrar'
LOGIN_REDIRECT_URL = 'facturacion:facturas'
LOGOUT_REDIRECT_URL = 'entrar'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}