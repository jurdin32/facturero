# Facturero

Facturación electrónica del SRI para el Ecuador, con contabilidad, caja, inventario y
reportes. Cada comprobante se firma, se envía y se consulta al Servicio de Rentas
Internas; lo que el SRI devuelve se enseña tal cual, con su motivo, en la ficha del
comprobante.

Está hecho con **Django 6** y se apoya en dos paquetes de la casa:

| Paquete | Para qué |
|---|---|
| [`factec`](https://github.com/jurdin32/factec) | Firma XAdES, envío y autorización en el SRI, modelos de los comprobantes, RIDE. |
| [`personalize_options`](https://github.com/jurdin32/personalize_options) | Roles y permisos de lectura/escritura por opción, con sus propias tablas. |

## Qué trae

- **Facturar**: la hoja de factura, con el catálogo de productos, el cliente traído del
  catasto del SRI y el cálculo de IVA, descuentos y totales.
- **Los demás comprobantes**: notas de crédito y de débito, liquidaciones de compra,
  guías de remisión y comprobantes de retención (los códigos de retención salen del
  catálogo del SRI que se carga en la base).
- **Catálogo e inventario**: clientes, productos y servicios, conductores, vehículos,
  existencias y kardex.
- **Caja del turno**: apertura, ingresos y egresos, cierre con **desglose de billetes y
  monedas** y **acta de cierre en PDF**. Sin caja abierta no se factura.
- **Supervisión de la caja** (aparte, con su propio permiso): revisión de los cuadres
  cerrados —**aprobar** o **dejar observado**, con quién y cuándo— y **vales de caja**
  para cobrar los faltantes.
- **Contabilidad**: plan de cuentas, asientos, libro diario y mayor, balance de
  comprobación, estado de resultados, estado de situación financiera, flujos y
  patrimonio, y los anexos del SRI (ATS, REOC y RDEP).
- **Reportes y estadísticas**: 17 reportes de ventas, comprobantes, compras,
  contabilidad e inventario, con filtros de período (día, semana, mes, trimestre, año,
  rango y todo el historial) y salidas en **pantalla, PDF y Excel**, siempre con el logo
  del emisor o, si no hay, el de Factiz. Incluye ventas por usuario.
- **Manual del sistema** dentro de la aplicación, con las capturas de cada pantalla.
- **Usuarios, roles y permisos**: se crean desde la aplicación (no hace falta el admin),
  con permisos agrupados por **categorías**; los botones que escriben se esconden a quien
  solo puede leer.

## Puesta en marcha

Hace falta **Python 3.12 o superior** y una base de datos (viene con SQLite).

```bash
git clone https://github.com/jurdin32/facturero.git
cd facturero
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Los dos paquetes de la casa, en modo editable si los va a tocar:
pip install -e ~/Desktop/Scripts/factec -e ~/Desktop/Scripts/personalize_options

python manage.py migrate
python manage.py cargar_codigos_retencion     # el catálogo de retenciones del SRI
python manage.py createsuperuser
python manage.py runserver
```

Después, en la aplicación:

1. **Configuración del SRI**: el asistente de cuatro pasos (emisor, ambiente y
   secuenciales, certificado `.p12` y comprobación).
2. **Roles y permisos**: cree los roles que hagan falta y márqueles sus opciones.
3. **Usuarios y sus roles**: dé de alta a la gente y asígnele su rol.
4. **Caja del turno**: abra la caja antes de la primera factura.

## Permisos

Los roles viven en la base y se administran desde la aplicación. En `settings.py`:

```python
PERSONALIZE_OPTIONS = {
    "MODO": "abierto",        # «abierto»: sin rol se puede todo; «cerrado»: solo lo que el rol permita
    "SUPERUSUARIOS_TODO": True,  # los superusuarios pueden todo aunque no tengan rol
}
```

En las plantillas, los controles de escritura se esconden así:

```django
{% load personalize_options %}
{% puede_escribir "clientes" as puede_escribir %}
{% if puede_escribir %}<a class="button primary" href="…">Nuevo cliente</a>{% endif %}
```

## Pruebas

```bash
python manage.py test
```

Son **301 pruebas**: los comprobantes de punta a punta, la caja y su acta, la
supervisión de los cuadres y los vales, los reportes en sus tres salidas, los
períodos, los permisos y el menú.

Todos los **PDF** —los reportes, el acta de cierre y los vales— salen de
**plantillas HTML** y de la hoja de estilo de imprenta `static/css/papel.css`,
convertidas con WeasyPrint (`facturero/papel.py`). Así lo impreso y lo que se ve
en pantalla se escribe una sola vez.

## En producción

- `deploy/systemd/` trae los servicios del worker, el reloj de Celery y Flower, con
  `env.ejemplo` para las variables.
- WeasyPrint necesita las bibliotecas **Pango** del sistema: en macOS
  `brew install pango`, en Debian/Ubuntu `apt install libpango-1.0-0 libpangoft2-1.0-0`.
- El certificado del emisor y la contraseña se guardan cifrados en la base; el archivo
  `.p12`, la base y la carpeta `media/` **no van al repositorio** (están en `.gitignore`).
- Los estáticos se sirven con `collectstatic`; en desarrollo los sirve Django.

## Lo que el sistema no hace

No inventa datos fiscales: los códigos de retención, las tarifas de IVA y los
documentos son los que publica el SRI. Si el SRI devuelve un error, el sistema lo
muestra con su identificador y su texto para que se corrija; no lo disimula.
