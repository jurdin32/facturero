"""El asistente de configuración del SRI, en cuatro pasos.

La configuración del emisor —quién factura, en qué ambiente, con qué serie y con
qué certificado de firma— se hacía en el admin de Django. Aquí se hace en la
interfaz, en cuatro pasos, con lo que falta señalado y sin salir de la pantalla.

El paquete factec se queda con lo difícil: su modelo valida el RUC, el
establecimiento y los campos adicionales, sabe consultar el catastro del SRI y
abre el ``.p12`` para comprobar la contraseña antes de guardarla cifrada. Esta
pantalla solo conduce el proceso y enseña lo que dice el paquete.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.checks import run_checks
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from factec.catalogos import Ambiente
from factec.django import ajustes as ajustes_sri, conf, sri_datos
from factec.django.models import ConfiguracionEmisor, Secuencial, TipoComprobante
from factec.excepciones import ErrorFacturacion

from facturero.marco import marco
from personalize_options.decoradores import (
    exigir_escritura,
    requiere_escritura,
    requiere_lectura,
)

from .forms import (
    FormularioCertificado,
    FormularioEmisor,
    FormularioLogo,
    FormularioSecuenciales,
    FormularioSRI,
)
from .models import LogoEmisor

__all__ = ["sri", "otra", "probar_sri", "logo"]


#: Los cuatro pasos, en orden. El nombre de cada uno sale en la barra de progreso.
PASOS = (
    {"numero": 1, "titulo": "Emisor", "que": "Quién factura y qué declaró en el SRI"},
    {"numero": 2, "titulo": "SRI y secuenciales", "que": "Ambiente, serie y numeración"},
    {"numero": 3, "titulo": "Certificado", "que": "El archivo de firma y su contraseña"},
    {"numero": 4, "titulo": "Comprobar", "que": "Que todo esté listo para emitir"},
)

#: Lo que se copia al añadir una segunda configuración (mismo emisor, otro ambiente).
CAMPOS_QUE_SE_COPIAN = (
    "ruc",
    "razon_social",
    "nombre_comercial",
    "dir_matriz",
    "dir_establecimiento",
    "obligado_contabilidad",
    "contribuyente_especial",
    "agente_retencion",
    "regimen",
    "categoria",
    "campos_adicionales",
    "estab",
    "pto_emi",
    "clave_certificado_cifrada",
)


# ------------------------------------------------------------------ el asistente


@login_required
@requiere_lectura("configuracion")
def sri(request: HttpRequest) -> HttpResponse:
    """El asistente: enseña el paso pedido y guarda el que se envíe."""
    configuracion = _la_configuracion(request)
    paso = _paso_pedido(request)
    if request.method == "POST":
        exigir_escritura(request, "configuracion")
        return _guardar(request, configuracion, paso)
    return _pintar(request, configuracion, paso)


@login_required
@require_POST
@requiere_escritura("configuracion")
def activar(request: HttpRequest, pk: int) -> HttpResponse:
    """Deja esta configuración como la que se usa y apaga las demás.

    Es el interruptor de pruebas/producción: la configuración activa es la que
    firma y la que fija el ambiente, y el ajuste ``sri_ambiente`` se mueve con
    ella para que las dos cosas no puedan quedar en desacuerdo.
    """
    from django.shortcuts import get_object_or_404

    configuracion = get_object_or_404(ConfiguracionEmisor, pk=pk)
    configuracion.activo = True
    configuracion.save()
    en_produccion = int(configuracion.ambiente) == int(Ambiente.PRODUCCION)
    ajustes_sri.poner("sri_ambiente", "produccion" if en_produccion else "pruebas")
    conf.limpiar_cache()

    if en_produccion:
        messages.warning(
            request,
            f"Ahora se usa «{configuracion.nombre}»: los comprobantes que se emitan "
            "tendrán validez legal ante el SRI.",
        )
    else:
        messages.success(
            request,
            f"Ahora se usa «{configuracion.nombre}»: los comprobantes son de pruebas, "
            "sin validez fiscal.",
        )
    return redirect(_url(1, configuracion))


@login_required
@require_POST
@requiere_escritura("configuracion")
def otra(request: HttpRequest) -> HttpResponse:
    """Añade una segunda configuración: la de producción, o la de pruebas.

    Se copia la que se estaba viendo (mismo emisor y misma firma) y se le cambia
    el ambiente, que es para lo que se quiere otra ficha. La nueva queda **sin
    activar**: la que se usa se elige después, con un botón, para que no cambie
    el ambiente de facturación sin querer.
    """
    original = _la_configuracion(request)
    en_produccion = original is not None and int(original.ambiente) == int(Ambiente.PRODUCCION)
    ambiente = int(Ambiente.PRUEBAS) if en_produccion else int(Ambiente.PRODUCCION)

    copia = ConfiguracionEmisor(
        nombre="Pruebas" if ambiente == int(Ambiente.PRUEBAS) else "Producción",
        ambiente=ambiente,
        activo=False,
    )
    if original is not None:
        for campo in CAMPOS_QUE_SE_COPIAN:
            setattr(copia, campo, getattr(original, campo))
        if original.certificado:
            copia.certificado = original.certificado.name
    copia.save()

    conf.limpiar_cache()
    donde = "producción" if ambiente == int(Ambiente.PRODUCCION) else "pruebas"
    messages.success(
        request,
        f"«{copia.nombre}» queda lista para {donde}, sin activar. Repase sus datos "
        "—el RUC y la serie se han copiado— y, cuando esté conforme, use su botón "
        "«Usar…» en la lista de configuraciones.",
    )
    return redirect(_url(1, copia))


@login_required
@require_POST
@requiere_escritura("configuracion")
def logo(request: HttpRequest) -> HttpResponse:
    """Sube —o quita— el logo que el emisor pone en el RIDE.

    Va en su propio envío y no en el paso 1 del asistente para que se pueda
    cambiar sin tocar los datos fiscales, y para que el archivo viaje solo.
    """
    configuracion = _la_configuracion(request)
    if configuracion is None:
        messages.warning(request, "Todavía no hay configuración del emisor.")
        return redirect(_url(1))

    if request.POST.get("quitar"):
        LogoEmisor.objects.filter(emisor=configuracion).delete()
        messages.success(request, "Logo quitado: el RIDE volverá a salir sin imagen.")
        return redirect(_url(1, configuracion))

    actual = LogoEmisor.de(configuracion)
    formulario = FormularioLogo(request.POST, request.FILES, instance=actual)
    if not formulario.is_valid():
        primero = next(iter(formulario.errors.values()), ["No se pudo guardar el logo."])[0]
        messages.error(request, primero)
        return redirect(_url(1, configuracion))

    guardado = formulario.save(commit=False)
    guardado.emisor = configuracion
    guardado.save()
    messages.success(request, "Logo guardado: ya sale en el RIDE y en la factura impresa.")
    return redirect(_url(1, configuracion))


@login_required
@require_POST
@requiere_lectura("configuracion")
def probar_sri(request: HttpRequest) -> HttpResponse:
    """Pide el RUC al catastro del SRI: así se sabe si hay con él quien hable."""
    configuracion = _la_configuracion(request)
    if configuracion is None:
        messages.warning(request, "Todavía no hay configuración del emisor.")
        return redirect(_url(1))

    try:
        resultado = sri_datos.consultar_datos(configuracion.ruc)
    except ErrorFacturacion as exc:
        messages.error(request, f"No se pudo contactar con el SRI: {exc}")
        return redirect(_url(4, configuracion))

    if not resultado.encontrado:
        messages.error(request, f"El SRI no devolvió datos para el RUC {configuracion.ruc}.")
        return redirect(_url(4, configuracion))

    datos = resultado.datos
    messages.success(
        request,
        f"El SRI respondió: {datos.razon_social} · {datos.estado or 'sin estado'} · "
        f"{datos.regimen or 'sin régimen'}.",
    )
    for aviso in resultado.avisos:
        messages.warning(request, aviso)
    return redirect(_url(4, configuracion))


# --------------------------------------------------------------------- guardar


def _guardar(request: HttpRequest, configuracion: Any, paso: int) -> HttpResponse:
    """Despacha el envío al paso que lo manda."""
    que = (request.POST.get("que") or "").strip()
    if configuracion is None and paso != 1:
        messages.info(request, "Empiece por decir quién emite.")
        return redirect(_url(1))
    if que == "secuenciales":
        return _guardar_secuenciales(request, configuracion)
    if paso == 1:
        return _guardar_emisor(request, configuracion)
    if paso == 2:
        return _guardar_sri(request, configuracion)
    if paso == 3:
        return _guardar_certificado(request, configuracion)
    return redirect(_url(4, configuracion))


def _guardar_emisor(request: HttpRequest, configuracion: Any) -> HttpResponse:
    formulario = FormularioEmisor(
        request.POST, instance=configuracion or ConfiguracionEmisor()
    )
    if formulario.is_valid():
        guardado = formulario.save()
        conf.limpiar_cache()
        if formulario.completados:
            messages.success(
                request, "El SRI completó " + _enumerar(formulario.completados) + "."
            )
        for aviso in formulario.avisos:
            messages.warning(request, aviso)
        messages.success(request, "Datos del emisor guardados.")
        return redirect(_url(2, guardado))
    messages.error(request, "Revise lo que está marcado en rojo.")
    return _pintar(request, configuracion, 1, formulario=formulario)


def _guardar_sri(request: HttpRequest, configuracion: Any) -> HttpResponse:
    formulario = FormularioSRI(request.POST, instance=configuracion)
    if formulario.is_valid():
        guardado = formulario.save()
        conf.limpiar_cache()
        messages.success(request, "Ambiente y serie guardados.")
        return redirect(_url(2, guardado))
    messages.error(request, "Revise lo que está marcado en rojo.")
    return _pintar(request, configuracion, 2, formulario=formulario)


def _guardar_secuenciales(request: HttpRequest, configuracion: Any) -> HttpResponse:
    formset = _formset_de_secuenciales(configuracion, request.POST)
    if formset.is_valid():
        for formulario in formset:
            datos = formulario.cleaned_data
            Secuencial.objects.update_or_create(
                tipo_comprobante=datos["tipo_comprobante"],
                estab=datos["estab"],
                pto_emi=datos["pto_emi"],
                ambiente=datos["ambiente"],
                defaults={"ultimo": datos["ultimo"]},
            )
        messages.success(request, "Secuenciales guardados.")
        return redirect(_url(2, configuracion))
    messages.error(request, "Revise los secuenciales.")
    return _pintar(request, configuracion, 2, formset=formset)


def _guardar_certificado(request: HttpRequest, configuracion: Any) -> HttpResponse:
    formulario = FormularioCertificado(request.POST, request.FILES, instance=configuracion)
    if formulario.is_valid():
        formulario.save()
        conf.limpiar_cache()
        for aviso in formulario.avisos:
            messages.warning(request, aviso)
        if (formulario.cleaned_data.get("clave_certificado") or "").strip() or formulario.cleaned_data.get("certificado"):
            messages.success(request, "Certificado guardado con su contraseña cifrada.")
        else:
            messages.info(request, "El certificado ya estaba puesto: no se cambió nada.")
        return redirect(_url(4, configuracion))
    messages.error(request, "Revise lo que está marcado en rojo.")
    return _pintar(request, configuracion, 3, formulario=formulario)


# ----------------------------------------------------------------------- pintar


def _pintar(
    request: HttpRequest,
    configuracion: Any,
    paso: int,
    formulario: Any = None,
    formset: Any = None,
) -> HttpResponse:
    """Pinta el asistente en el paso pedido, con el estado de los cuatro."""
    if configuracion is None and paso > 1:
        messages.info(request, "Empiece por decir quién emite.")
        return redirect(_url(1))

    if formulario is None:
        formulario = _formulario_del_paso(paso, configuracion)
    if formset is None and paso == 2:
        formset = _formset_de_secuenciales(configuracion)

    # El certificado se abre una sola vez por pantalla y se reutiliza: es lo más
    # caro de pintar (hay que descifrar el .p12 y leerlo).
    firma = configuracion.revisar_certificado() if configuracion else None
    estado = _estado(configuracion, firma)
    pasos = [{**ficha, **estado[ficha["numero"]]} for ficha in PASOS]
    hechos = sum(1 for ficha in pasos if ficha["hecho"])

    contexto: Dict[str, Any] = {
        **marco(request),
        "pasos": pasos,
        "paso": paso,
        "porcentaje": round(100 * hechos / len(PASOS)),
        "configuracion": configuracion,
        "configuraciones": ConfiguracionEmisor.objects.all().order_by("-activo", "nombre"),
        # La que de verdad se usa, para poder decir si se está mirando otra.
        "en_uso": ConfiguracionEmisor.objects.filter(activo=True).first(),
        "firma": firma,
        "firma_titular": _nombre_comun(firma.titular) if firma else "",
        "firma_emisor": _nombre_comun(firma.emisor) if firma else "",
        "formulario": formulario,
        "formset": formset,
        "logo": LogoEmisor.de(configuracion),
        "comprobaciones": _comprobaciones(firma) if paso == 4 else None,
    }
    return render(request, "configuracion/sri.html", contexto)


def _formulario_del_paso(paso: int, configuracion: Any) -> Any:
    """El formulario del paso, con lo que haya guardado por defecto."""
    clases = {1: FormularioEmisor, 2: FormularioSRI, 3: FormularioCertificado}
    clase = clases.get(paso)
    if clase is None:
        return None
    return clase(instance=configuracion or ConfiguracionEmisor())


def _formset_de_secuenciales(configuracion: Any, datos: Any = None) -> Any:
    """Una fila por tipo de comprobante, con el último número usado.

    Las que todavía no están en la base salen con el cero: al guardar se crean.
    """
    filtro = {
        "estab": configuracion.estab,
        "pto_emi": configuracion.pto_emi,
        "ambiente": configuracion.ambiente,
    }
    guardados = {
        fila.tipo_comprobante: fila for fila in Secuencial.objects.filter(**filtro)
    }
    iniciales = [
        {
            **filtro,
            "tipo_comprobante": tipo,
            "ultimo": guardados[tipo].ultimo if tipo in guardados else 0,
        }
        for tipo, _ in TipoComprobante.choices
    ]
    return FormularioSecuenciales(datos, initial=iniciales, prefix="secuencial")


# ------------------------------------------------------------------- el estado


def _estado(configuracion: Any, firma: Any = None) -> Dict[int, Dict[str, Any]]:
    """Qué pasos están listos y qué le falta a cada uno. Se mira lo guardado.

    El informe del certificado se puede pasar hecho, para no abrir el ``.p12`` dos
    veces en la misma pantalla.
    """
    if configuracion is None:
        return {
            ficha["numero"]: {"hecho": False, "falta": "No hay configuración del emisor."}
            for ficha in PASOS
        }

    sin_emisor = [
        nombre
        for nombre, campo in (
            ("el RUC", "ruc"),
            ("la razón social", "razon_social"),
            ("la dirección de la matriz", "dir_matriz"),
        )
        if not (getattr(configuracion, campo) or "").strip()
        or (campo == "ruc" and len(configuracion.ruc.strip()) != 13)
    ]
    serie_corta = [
        nombre
        for nombre, campo in (("el establecimiento", "estab"), ("el punto de emisión", "pto_emi"))
        if len((getattr(configuracion, campo) or "").strip()) != 3
    ]
    if firma is None:
        firma = configuracion.revisar_certificado()
    mensajes = _chequeos()
    errores = [mensaje for mensaje in mensajes if mensaje.is_serious()]

    return {
        1: {
            "hecho": not sin_emisor,
            "falta": f"Falta {_enumerar(sin_emisor)}." if sin_emisor else "",
        },
        2: {
            "hecho": not serie_corta,
            "falta": (
                f"{_enumerar(serie_corta).capitalize()} tiene que ser de tres dígitos."
                if serie_corta
                else ""
            ),
        },
        3: {
            "hecho": firma.ok,
            "falta": "" if firma.ok else (firma.problemas or ["Falta el certificado de firma."])[0],
        },
        4: {
            "hecho": bool(not sin_emisor and not serie_corta and firma.ok and not errores),
            "falta": "" if not errores else f"{len(errores)} cosa(s) por arreglar.",
        },
    }


def _comprobaciones(firma: Any) -> Dict[str, Any]:
    """Lo que dice el propio paquete: los chequeos y el informe de la firma."""
    mensajes = _chequeos()
    return {
        "mensajes": mensajes,
        "hay_errores": any(mensaje.is_serious() for mensaje in mensajes),
        "firma": firma,
    }


def _chequeos() -> List[Any]:
    """Los mismos chequeos que corre ``manage.py check`` para la app del SRI."""
    return list(run_checks(tags=["factec"]))


# ---------------------------------------------------------------------- útiles


def _la_configuracion(request: HttpRequest) -> Optional[Any]:
    """La configuración con la que se está trabajando.

    Se elige con ``?c=<pk>`` (o en el POST); por defecto, la activa. Así se puede
    tener la de pruebas y la de producción y pasar de una a otra sin perderse.
    """
    cual = (request.GET.get("c") or request.POST.get("c") or "").strip()
    if cual.isdigit():
        elegida = ConfiguracionEmisor.objects.filter(pk=int(cual)).first()
        if elegida is not None:
            return elegida
    return conf.configuracion_activa() or ConfiguracionEmisor.objects.first()


def _paso_pedido(request: HttpRequest) -> int:
    """El paso que se está viendo o enviando (1 si no dice nada)."""
    crudo = (request.POST.get("paso") or request.GET.get("paso") or "1").strip()
    if crudo.isdigit() and 1 <= int(crudo) <= len(PASOS):
        return int(crudo)
    return 1


def _url(paso: int, configuracion: Any = None) -> str:
    """La dirección del paso, con la configuración que se esté viendo."""
    destino = f"{reverse('configuracion:sri')}?paso={paso}"
    if configuracion is not None and getattr(configuracion, "pk", None):
        destino += f"&c={configuracion.pk}"
    return destino


def _enumerar(partes: Any) -> str:
    """«a, b y c», para los mensajes."""
    lista = [str(parte) for parte in partes if parte]
    if not lista:
        return ""
    if len(lista) == 1:
        return lista[0]
    return ", ".join(lista[:-1]) + " y " + lista[-1]


def _nombre_comun(texto: Any) -> str:
    """El nombre a secas de un titular o de una casa certificadora.

    El certificado lo da como ``C=EC,O=…,OU=…,CN=Juan Pérez``: en pantalla eso no
    hay quien lo lea, así que se enseña el nombre común.
    """
    for parte in reversed(str(texto or "").split(",")):
        limpio = parte.strip()
        if limpio.upper().startswith("CN="):
            return limpio[3:].strip()
    return str(texto or "")
