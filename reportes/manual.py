"""El manual de uso: qué hace cada pantalla y cómo se recorre el sistema.

Las capturas viven en ``static/img/manual/``; si alguna falta, la sección se queda
sin imagen y sigue explicando el paso, así el manual nunca se rompe.
"""

from __future__ import annotations

from typing import Any, Optional

from django.contrib.staticfiles import finders
from django.templatetags.static import static

__all__ = ["INDICE", "SECCIONES", "secciones"]

#: Las extensiones que se buscan para cada captura.
EXTENSIONES = ("png", "jpg", "jpeg", "webp")

#: Las secciones del manual, en el orden en que se leen.
SECCIONES: tuple[dict[str, Any], ...] = (
    {
        "clave": "entrar",
        "titulo": "Entrar y bloquear la pantalla",
        "capturas": ("entrar",),
        "resumen": (
            "Se entra con el usuario y la clave que cree el administrador. La pantalla se "
            "puede bloquear sin cerrar la sesión: al desbloquearla se vuelve a la misma "
            "página en la que se estaba."
        ),
        "pasos": (
            "Escriba su usuario y su clave, y pulse «Entrar».",
            "Para dejar el puesto solo un momento, use el botón «Bloquear» de la barra superior.",
            "Al volver, escriba su clave para retomar la sesión donde la dejó.",
            "Las opciones del menú dependen de los permisos de su rol: si no ve alguna, "
            "pídale al administrador que se la habilite.",
        ),
    },
    {
        "clave": "tablero",
        "titulo": "El tablero: lo que va pasando",
        "capturas": ("tablero",),
        "resumen": (
            "Es la primera pantalla. Resume lo facturado en los últimos días, lo que pide "
            "atención y lo que se puede hacer ahora mismo."
        ),
        "pasos": (
            "Cambie el período del gráfico con el selector de días.",
            "Revise los contadores de arriba: comprobantes, autorizaciones y pendientes.",
            "Los avisos de la derecha llevan a la pantalla que hay que resolver.",
        ),
    },
    {
        "clave": "facturar",
        "titulo": "Emitir una factura",
        "capturas": ("facturar",),
        "resumen": (
            "El formulario se parece al comprobante que va a salir: cabecera, líneas y "
            "totales. Al guardar se firma y se envía al SRI."
        ),
        "pasos": (
            "Elija el cliente por su identificación: el sistema lo busca en el catálogo y, "
            "si no está, lo trae del catastro del SRI para cédula y RUC.",
            "Añada las líneas con el buscador de productos. La cantidad, el precio y el "
            "descuento se calculan solos y el IVA sale de la tarifa del producto.",
            "Revise la forma de pago y el plazo; guarde como borrador si aún no está seguro.",
            "Para facturar tiene que estar abierta su caja del turno: si no lo está, la "
            "pantalla se lo dice y lo lleva a abrirla.",
            "Al emitir, el comprobante se firma, se envía y queda con su estado. Si el SRI lo "
            "devuelve, el motivo se lee en la ficha del comprobante.",
        ),
    },
    {
        "clave": "comprobantes",
        "titulo": "Los demás comprobantes",
        "capturas": ("comprobantes", "comprobante-nuevo"),
        "resumen": (
            "Notas de crédito y de débito, liquidaciones de compra, guías de remisión y "
            "comprobantes de retención. Todos siguen el mismo camino: se llenan, se emiten y "
            "se siguen por su estado."
        ),
        "pasos": (
            "La nota de crédito devuelve lo vendido: el buscador de comprobantes trae las "
            "líneas del documento original.",
            "La guía de remisión lleva destinatarios, transportista y vehículo; se puede "
            "apoyar en una factura del mismo cliente.",
            "En la retención, el concepto se busca en el catálogo del SRI: al elegirlo se "
            "completan el impuesto y el porcentaje.",
            "Cada ficha enseña la clave de acceso, el estado, el RIDE y el XML, y permite "
            "reintentar el envío o volver a consultar al SRI.",
        ),
    },
    {
        "clave": "catalogos",
        "titulo": "Clientes, productos, conductores y vehículos",
        "capturas": ("catalogos",),
        "resumen": (
            "El catálogo es la base de todo: de aquí salen las líneas de la factura, las "
            "existencias del inventario y los datos de la guía de remisión."
        ),
        "pasos": (
            "Las tablas se leen de corrido; para corregir algo, use el lápiz de la fila y el "
            "formulario se abre en una ventana.",
            "En el producto se fija el precio, la tarifa de IVA y el mínimo de existencias.",
            "En el cliente se guardan la identificación, la dirección y el correo para el "
            "envío del comprobante.",
        ),
    },
    {
        "clave": "inventario",
        "titulo": "Inventario y kardex",
        "capturas": ("inventario",),
        "resumen": (
            "Cuánto hay de cada producto, con su valor y el aviso de los que están bajo el "
            "mínimo. El kardex es el libro de movimientos de un producto, con su saldo."
        ),
        "pasos": (
            "Filtre por texto o marque «solo bajo el mínimo» para ver lo que hay que reponer.",
            "Abra el kardex de un producto para registrar una entrada, una salida o un ajuste.",
            "Las salidas por factura las pone el sistema al emitir; no se registran a mano.",
        ),
    },
    {
        "clave": "contabilidad",
        "titulo": "Contabilidad",
        "capturas": ("contabilidad",),
        "resumen": (
            "El plan de cuentas, los asientos, los libros y los estados financieros, además "
            "de los anexos del SRI (ATS, REOC y RDEP)."
        ),
        "pasos": (
            "Cargue primero el plan de cuentas y la configuración contable.",
            "Los asientos de ventas y compras los propone el sistema; revíselos y contabilícelos.",
            "Los libros y los estados se piden por rango de fechas y se descargan en PDF o Excel.",
            "Los anexos se generan por mes y se descargan en el formato que pide el SRI.",
        ),
    },
    {
        "clave": "caja",
        "titulo": "La caja del turno",
        "capturas": ("caja", "caja-cierre"),
        "resumen": (
            "Cada usuario abre su caja al empezar y la cierra al terminar. Sin caja abierta "
            "no se puede facturar: así el efectivo que se cobra tiene dónde constar y el "
            "arqueo del día cuadra. El cierre se hace contando los billetes y las monedas, y "
            "deja un acta en PDF que se firma."
        ),
        "pasos": (
            "Abra la caja con el efectivo inicial del turno.",
            "Los cobros en efectivo de las facturas entran solos; lo demás se registra con "
            "«Registrar movimiento», que se abre en su ventana.",
            "Al cerrar, pulse «Cerrar caja»: se abre la ventana del arqueo con una línea por "
            "billete y moneda. Escriba cuántos hay y el total sale solo.",
            "El sistema compara con el saldo esperado y guarda la diferencia, si la hay.",
            "Descargue el «Acta de cierre en PDF» desde la pantalla o desde «Cierres anteriores».",
        ),
    },
    {
        "clave": "supervision-caja",
        "titulo": "Supervisión: cuadres y vales",
        # Sin capturas todavía: la sección se lee igual y el manual no se rompe.
        "capturas": (),
        "resumen": (
            "La revisión de la caja es aparte de la caja del turno, porque no es cosa del cajero: "
            "vive en el apartado «Supervisión» del menú y tiene su propio permiso. Ahí se aprueban "
            "los cuadres, se dejan observados y se cobran los faltantes con vales."
        ),
        "pasos": (
            "Abra «Supervisión → Revisión de caja». La pantalla abre en el día de hoy —las cajas "
            "abiertas ahora y las que ya se cerraron—; con las pestañas de arriba se va a la "
            "semana, al mes o a todo el historial, y con las de abajo se separa lo que sigue sin "
            "revisar de lo aprobado y lo observado.",
            "Mire el cuadre: saldo inicial, ingresos, egresos, esperado, contado y lo que falta. "
            "Si el cajero contó billete por billete, «Desglose de lo contado» lo abre.",
            "Escriba una nota si hace falta y pulse «Aprobar el cuadre» o «Dejar observado». El "
            "sistema guarda quién revisó, cuándo y con qué nota; también sale en el acta en PDF.",
            "Si el cuadre tiene faltante, pulse «Cobrar … con un vale»: se abre el vale con el "
            "importe y el responsable ya puestos. No deja cobrar más de lo que falta.",
            "En «Supervisión → Vales de caja» está el libro completo. Un vale pendiente se cobra "
            "con «Cobrar» —queda la fecha del cobro— o se anula si no tenía por qué existir.",
            "Cada vale se imprime con «Imprimir»: se abre en PDF —con el logo, el número, el "
            "importe, el motivo y las dos firmas— y desde ahí se imprime o se guarda.",
            "Para que alguien entre aquí hace falta darle, en «Roles y permisos», la categoría "
            "«Supervisión»; un cajero con su caja no la ve.",
        ),
    },
    {
        "clave": "reportes",
        "titulo": "Reportes y estadísticas",
        "capturas": ("reportes", "reporte-ventas"),
        "resumen": (
            "Todos los listados del sistema en un solo sitio, con filtros de período y tres "
            "salidas: pantalla, PDF y Excel. Todos llevan el logo del emisor o, si no hay, el "
            "de Factiz."
        ),
        "pasos": (
            "Elija el reporte en el índice; cada tarjeta dice qué trae y con qué norma se "
            "relaciona. Hay libros de ventas y compras, estados financieros, inventario y el "
            "control de quién vendió (ventas por usuario).",
            "Elija el período: hoy, ayer, semana, mes, trimestre, año, últimos 30 días, todo el "
            "historial o un rango de fechas escrito a mano.",
            "Pulse «Ver» para leerlo en pantalla, «PDF» para abrirlo en el navegador —de ahí se "
            "guarda o se imprime— y «Excel» para descargarlo y seguir trabajando.",
            "El período y la cuenta elegidos viajan en la dirección: se puede guardar el enlace "
            "de un reporte y volver a él tal cual.",
        ),
    },
    {
        "clave": "ajustes",
        "titulo": "Ajustes de la aplicación",
        "capturas": (),
        "resumen": (
            "La configuración que antes se escribía en el archivo de ajustes del proyecto: el "
            "modo de los permisos, el bloqueo de la pantalla, el ambiente del SRI, si se "
            "descuenta el inventario al facturar o si se contabiliza al autorizar. Vive en la "
            "base de datos y se cambia desde aquí: cada paquete declara sus ajustes y la "
            "migración los siembra."
        ),
        "pasos": (
            "Abra «Sistema → Ajustes de la aplicación».",
            "Cada bloque dice qué paquete lo declara —personalize_options, factec, inventario, "
            "seguridad…— y para qué sirve cada ajuste.",
            "Escriba el valor nuevo (sí/no, un número o un texto) y pulse «Guardar los ajustes»: "
            "vale al momento, sin reiniciar nada.",
            "El nombre del ajuste no se escribe: es la clave con la que lo lee el código y viene "
            "de la declaración del paquete.",
            "Los secretos, como la clave que cifra la contraseña del certificado, se guardan y "
            "se muestran ocultos: se ven, no se copian.",
        ),
    },
    {
        "clave": "configuracion",
        "titulo": "Configuración del SRI",
        "capturas": ("configuracion",),
        "resumen": (
            "El asistente en cuatro pasos: emisor, ambiente y secuenciales, certificado y "
            "comprobación. Sin esto no se puede firmar nada."
        ),
        "pasos": (
            "Paso 1: datos del emisor —RUC, razón social, direcciones y logo— y el ambiente.",
            "Paso 2: la serie (establecimiento y punto de emisión) y el secuencial de cada tipo "
            "de comprobante.",
            "Paso 3: suba el certificado .p12 y escriba su contraseña; se guarda cifrada.",
            "Paso 4: revise las comprobaciones; en verde, el sistema está listo para emitir.",
        ),
    },
    {
        "clave": "seguridad",
        "titulo": "Usuarios, roles y permisos",
        "capturas": ("seguridad",),
        "resumen": (
            "Cada usuario entra con su cuenta y tiene uno o más roles. El rol dice qué "
            "opciones puede leer y cuáles puede modificar."
        ),
        "pasos": (
            "Cree el rol y márquele las opciones: lectura para mirar, escritura para guardar.",
            "Asigne el rol a los usuarios.",
            "En «Opciones de la aplicación» se ve el menú completo, con su dirección "
            "y su orden.",
            "Para cambiar el orden, use las flechas de la columna «Orden» de la "
            "propia lista —o las de «Opciones de la aplicación → Ordenar el menú»—: "
            "un toque sube o baja la opción dentro de su apartado y se guarda al "
            "momento. Arrastrando el título de un apartado en «Ordenar el menú» se "
            "mueve entero.",
        ),
    },
)

#: El índice del manual: el título de cada sección, para la barra lateral.
INDICE: tuple[tuple[str, str], ...] = tuple((seccion["clave"], seccion["titulo"]) for seccion in SECCIONES)


def _captura(nombre: Optional[str]) -> str:
    """La dirección de la captura, si el archivo está en ``static/img/manual/``."""
    if not nombre:
        return ""
    for extension in EXTENSIONES:
        ruta = f"img/manual/{nombre}.{extension}"
        if finders.find(ruta):
            return static(ruta)
    return ""


def secciones() -> list[dict[str, Any]]:
    """Las secciones del manual, con sus capturas resueltas."""
    return [
        {
            **seccion,
            "imagenes": [
                imagen
                for imagen in (_captura(nombre) for nombre in seccion.get("capturas", ()))
                if imagen
            ],
        }
        for seccion in SECCIONES
    ]


#: Qué hace cada opción del menú, en una línea. Las que no estén aquí salen igual en
#: el mapa —con su nombre y su dirección— para que ninguna quede sin documentar.
QUE_HACE: dict[str, str] = {
    "tablero": "Lo facturado en los últimos días, lo que pide atención y los avisos del turno.",
    "facturar": "La hoja de la factura: cliente, líneas del catálogo, IVA y totales.",
    "facturas": "Las facturas emitidas, con filtros por fecha, cliente y estado ante el SRI.",
    "notas_credito": "Devuelve o corrige una factura ya autorizada; trae sus líneas.",
    "notas_debito": "Cobra valores que no iban en la factura: intereses, gastos, ajustes.",
    "liquidaciones_compra": "Compra a un proveedor que no está obligado a facturar.",
    "guias_remision": "Transporte de bienes: destinatarios, transportista, vehículo y bienes.",
    "retenciones": "Retiene IVA, renta o ISD al proveedor con los códigos del SRI.",
    "productos": "Bienes y servicios con su precio, su tarifa de IVA y su mínimo.",
    "clientes": "Quién compra, con su identificación, dirección y correo.",
    "conductores": "Los transportistas de las guías de remisión.",
    "vehiculos": "Los vehículos que llevan la carga, por placa.",
    "inventario": "Existencias, valor y aviso de reposición; de aquí sale el kardex.",
    "caja": "El efectivo del turno: apertura, movimientos, cierre con desglose y acta.",
    "revision_caja": (
        "Los cuadres ya cerrados, para aprobarlos o dejarlos observados con su nota."
    ),
    "vales_caja": "Los vales de caja: cobrar un faltante o sacar efectivo a cuenta de alguien.",
    "ajustes": (
        "La configuración de la aplicación: el modo de los permisos, el bloqueo de la "
        "pantalla, el ambiente del SRI y lo demás que antes iba en settings.py."
    ),
    "estado_inicial": "El punto de partida de la contabilidad: activo, pasivo y patrimonio.",
    "plan_cuentas": "Las cuentas contables, con su grupo, su naturaleza y sus jerarquías.",
    "contabilidad": "El resumen del mes: movimiento, resultado y avisos del cierre.",
    "asientos": "Los asientos contables: se proponen, se revisan y se contabilizan.",
    "libro_diario": "Todos los asientos del período, línea por línea, en orden de fecha.",
    "libro_mayor": "El extracto de una cuenta: saldo anterior, movimientos y saldo final.",
    "balance_comprobacion": "Sumas y saldos por cuenta; comprueba que la partida doble cuadre.",
    "estados_financieros": "Estado de resultados, situación financiera, flujos y patrimonio.",
    "compras": "Las compras y gastos con comprobante, para el registro y el ATS.",
    "anexos_sri": "ATS, REOC y RDEP del mes, en el formato que pide el SRI.",
    "empleados": "Los empleados y lo que va al RDEP: sueldos, aportes y retenciones.",
    "configuracion_contable": "Qué cuentas usa el sistema para vender, comprar y retener.",
    "cierre_contable": "Cierra el ejercicio: asiento de cierre y apertura del siguiente.",
    "reportes": "El índice de los 17 reportes, con sus filtros de período.",
    "usuarios": "Quién entra al sistema, con su clave y sus roles.",
    "roles": "Los roles y sus permisos, por categorías y por opción.",
    "opciones": "El menú completo: categorías, opciones, su orden y su dirección.",
    "configuracion": "El asistente del SRI: emisor, secuencia, certificado y comprobación.",
    "manual": "Esta guía, con las capturas de cada pantalla.",
}


def _que_hace(clave: str) -> str:
    """La explicación de una opción: la suya o, si es un reporte, la del catálogo."""
    if clave in QUE_HACE:
        return QUE_HACE[clave]
    if clave.startswith("reporte_"):
        from . import catalogo

        definicion = catalogo.de(clave[len("reporte_"):])
        if definicion is not None:
            return definicion.descripcion
    return ""


def mapa_de_opciones() -> list[tuple[str, list[dict[str, str]]]]:
    """Todas las opciones del menú, por categoría, con lo que hace cada una.

    Se arma desde la base, no desde una lista escrita a mano: si mañana se añade una
    opción, aparece aquí sola —con su nombre y su dirección— aunque todavía no tenga
    explicación. Así ninguna opción queda sin documentar.
    """
    from personalize_options import opciones as registro

    mapa = []
    for categoria, opciones in registro.grupos(solo_activas=True):
        mapa.append(
            (
                categoria,
                [
                    {
                        "nombre": opcion.nombre,
                        "clave": opcion.clave,
                        "url": opcion.url,
                        "que": _que_hace(opcion.clave),
                    }
                    for opcion in opciones
                ],
            )
        )
    return mapa
