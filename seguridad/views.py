"""Las pantallas de la seguridad: los roles y quién los lleva.

Los roles y sus permisos los guarda el paquete ``personalize_options``; aquí está lo
que le falta al paquete, que es lo de la aplicación: las listas —con buscador, orden
y paginación— y el asistente para dejar un rol listo en tres pasos (el rol, sus
permisos y el repaso).

Las opciones que salen en el asistente son las del registro del paquete
(``personalize_options.opciones``), así que la lista de pantallas de la aplicación y
la de permisos son la misma: no hay forma de que una se quede sin protección.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse
from django.views.decorators.http import require_POST
from personalize_options.decoradores import (
    exigir_escritura,
    requiere_lectura,
    requiere_escritura,
)
from personalize_options import opciones as registro
from personalize_options.models import Nivel, Opcion, Permiso, Rol
from personalize_options.permisos import de as permisos_de

from facturero.marco import marco
from facturero.tablas import Columna, Tabla

from .forms import (
    FormularioUsuario,
    FormularioDatosDelRol,
    FormularioOpcion,
    FormularioPermisos,
    FormularioRoles,
    casillas_del_formulario,
)

__all__ = [
    "accion",
    "ajustes",
    "mover_opcion",
    "accion_opcion",
    "guardar_orden_menu",
    "opcion",
    "opciones",
    "ordenar_menu",
    "rol",
    "roles",
    "usuario",
    "usuarios",
]

#: Los tres pasos del asistente del rol, en orden.
PASOS = (
    {"numero": 1, "titulo": "El rol", "que": "Cómo se llama y quién lo lleva"},
    {"numero": 2, "titulo": "Permisos", "que": "Qué puede, opción por opción"},
    {"numero": 3, "titulo": "Resumen", "que": "El repaso antes de terminar"},
)


def _paso_pedido(request: HttpRequest) -> int:
    """El paso del asistente que se está viendo (1 si no se pide ninguno)."""
    pedido = request.GET.get("paso")
    if pedido and pedido.isdigit() and 1 <= int(pedido) <= len(PASOS):
        return int(pedido)
    return 1


def _los_pasos(objeto: Rol, paso: int) -> List[Dict[str, Any]]:
    """Los pasos con su estado: el que se ve, los que ya se pueden dar por hechos."""
    hay_rol = bool(objeto.pk)
    hay_permisos = bool(objeto.pk and objeto.permisos.exists())
    return [
        {
            **ficha,
            "activo": ficha["numero"] == paso,
            "hecho": (hay_rol and ficha["numero"] == 1) or (hay_permisos and ficha["numero"] == 2),
            # Los permisos de un rol que todavía no existe no se pueden marcar.
            "enlace": (
                f"{reverse('seguridad:rol', args=[objeto.pk])}?paso={ficha['numero']}"
                if hay_rol
                else ""
            ),
        }
        for ficha in PASOS
    ]


def _niveles_por_apartado(quien: Any) -> List[Tuple[str, List[Tuple[Opcion, str]]]]:
    """Lo que puede hoy, opción por opción, agrupado como el menú.

    En modo abierto, quien no tiene ningún rol puede todo: se enseña como si los
    roles le dieran escritura en todas las opciones, que es lo que pasa de verdad.
    """
    abierto = quien.es_abierto

    def nivel_de(opcion: Opcion) -> str:
        return quien.nivel(opcion.clave) or (Nivel.ESCRITURA.value if abierto else "")

    return [
        (grupo, [(opcion, nivel_de(opcion)) for opcion in opciones])
        for grupo, opciones in registro.grupos(solo_activas=True)
    ]


def _marcados(formulario: Any, request: HttpRequest, persona: Any) -> Set[int]:
    """Qué casillas dejar marcadas: lo que se acaba de enviar o lo que ya llevaba."""
    if formulario.is_bound:
        return {int(pk) for pk in request.POST.getlist("roles") if str(pk).isdigit()}
    return set(persona.roles.values_list("pk", flat=True))


# ------------------------------------------------------------------- roles


@login_required
@requiere_lectura("roles")
def roles(request: HttpRequest) -> HttpResponse:
    """Los roles, en una tabla con buscador, orden y paginación."""
    listado = Rol.objects.annotate(
        cuantos_usuarios=Count("usuarios", distinct=True),
        cuantas_opciones=Count("permisos", distinct=True),
        con_escritura=Count(
            "permisos", filter=Q(permisos__nivel=Nivel.ESCRITURA.value), distinct=True
        ),
    )
    tabla = Tabla(
        request,
        listado,
        columnas=[
            Columna("Estado", "activo", clase="col-estado"),
            Columna("Rol", "nombre"),
            Columna("Puede", "cuantas_opciones", clase="col-num"),
            Columna("Para modificar", "con_escritura", clase="col-num"),
            Columna("Usuarios", "cuantos_usuarios", clase="col-num"),
            Columna("", clase="col-acciones"),
        ],
        buscar_en=["nombre", "descripcion"],
        orden_por_omision="nombre",
    )

    contexto = {
        **marco(request),
        "tabla": tabla,
        "buscador": "Nombre o para qué es el rol",
        "cuantos": Rol.objects.count(),
        "cuantos_activos": Rol.objects.filter(activo=True).count(),
        "opciones_totales": len(registro.todas()),
    }
    return render(request, "seguridad/roles.html", contexto)


@login_required
@requiere_lectura("roles")
def rol(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """El asistente del rol: el rol, sus permisos y el resumen."""
    objeto = get_object_or_404(Rol, pk=pk) if pk else Rol()
    paso = _paso_pedido(request)
    if paso > 1 and not objeto.pk:
        # Los permisos y el resumen son de un rol que ya existe: sin él, al primero.
        paso = 1

    if request.method == "POST":
        return _guardar(request, objeto, paso)
    return _pintar(request, objeto, paso)


def _pintar(
    request: HttpRequest, objeto: Rol, paso: int, formulario: Any = None
) -> HttpResponse:
    """Pinta el paso pedido, con lo que ya tenga el rol."""
    if formulario is None:
        formulario = (
            FormularioDatosDelRol(instance=objeto)
            if paso == 1
            else FormularioPermisos(rol=objeto)
        )
    # Las casillas de los permisos se pintan en los pasos 2 y 3: si lo que se envió
    # era el formulario del rol, se arma uno de permisos con lo que ya tenga.
    permisos = (
        formulario
        if isinstance(formulario, FormularioPermisos)
        else FormularioPermisos(rol=objeto)
    )

    hay_rol = bool(objeto.pk)
    contexto = {
        **marco(request),
        "rol": objeto,
        "es_nuevo": not hay_rol,
        "paso": paso,
        "pasos": _los_pasos(objeto, paso),
        "formulario": formulario,
        "opciones_totales": len(registro.todas()),
        "grupos": casillas_del_formulario(permisos),
        # El resumen del último paso, con lo que va a quedar guardado. Un rol que
        # todavía no existe no tiene permisos ni usuarios: no se le puede preguntar.
        "niveles": [
            (
                grupo,
                [
                    (opcion, objeto.nivel(opcion.clave) if hay_rol else "")
                    for opcion in opciones
                ],
            )
            for grupo, opciones in registro.grupos(solo_activas=True)
        ],
        "cuantas_opciones": objeto.permisos.count() if hay_rol else 0,
        "con_escritura": (
            objeto.permisos.filter(nivel=Nivel.ESCRITURA.value).count() if hay_rol else 0
        ),
        "cuantos_usuarios": objeto.usuarios.count() if hay_rol else 0,
    }
    return render(request, "seguridad/rol.html", contexto)


def _guardar(request: HttpRequest, objeto: Rol, paso: int) -> HttpResponse:
    """Guarda el paso que se haya enviado y pasa al siguiente."""
    exigir_escritura(request, "roles")

    if paso == 3:  # el resumen no se guarda: es un repaso
        return redirect(f"{reverse('seguridad:rol', args=[objeto.pk])}?paso=3")

    if paso == 1:
        formulario = FormularioDatosDelRol(request.POST, instance=objeto)
        if formulario.is_valid():
            guardado = formulario.save()
            messages.success(request, f"Rol «{guardado.nombre}» guardado.")
            return redirect(f"{reverse('seguridad:rol', args=[guardado.pk])}?paso=2")
    else:
        if not objeto.pk:
            raise Http404("Los permisos son de un rol que todavía no existe.")
        formulario = FormularioPermisos(request.POST, rol=objeto)
        if formulario.is_valid():
            cuantas = formulario.guardar_en(objeto)
            messages.success(
                request,
                f"Permisos guardados: «{objeto.nombre}» puede {cuantas} de "
                f"{len(registro.todas())} opciones.",
            )
            return redirect(f"{reverse('seguridad:rol', args=[objeto.pk])}?paso=3")

    messages.error(request, "Revise lo que está marcado en rojo.")
    return _pintar(request, objeto, paso, formulario)


@login_required
@require_POST
@requiere_escritura("roles")
def accion(request: HttpRequest, pk: int, que: str) -> HttpResponse:
    """Apagar un rol, volver a encenderlo o borrarlo."""
    objeto = get_object_or_404(Rol, pk=pk)
    nombre = objeto.nombre

    if que == "activar":
        objeto.activo = True
        objeto.save()
        messages.success(request, f"Rol «{nombre}» activado.")
    elif que == "desactivar":
        objeto.activo = False
        objeto.save()
        messages.info(
            request,
            f"Rol «{nombre}» desactivado: quien lo lleve deja de tener lo que daba.",
        )
    elif que == "eliminar":
        cuantos = objeto.usuarios.count()
        objeto.delete()
        aviso = f"Rol «{nombre}» eliminado."
        if cuantos:
            aviso += f" {cuantos} usuario(s) se quedaron sin ese rol."
        messages.success(request, aviso)
    else:
        raise Http404(f"«{que}» no es algo que se le pueda hacer a un rol.")

    return redirect("seguridad:roles")


# ---------------------------------------------------------------- usuarios


@login_required
@requiere_lectura("usuarios")
def usuarios(request: HttpRequest) -> HttpResponse:
    """Quién hay y qué roles lleva cada uno, en tabla con buscador y páginas."""
    Persona = get_user_model()
    listado = (
        Persona.objects.prefetch_related("roles")
        .annotate(cuantos_roles=Count("roles", distinct=True))
    )
    tabla = Tabla(
        request,
        listado,
        columnas=[
            Columna("Usuario", "username"),
            Columna("Correo", "email"),
            Columna("Roles", "cuantos_roles", clase="col-num"),
            Columna("Último acceso", "last_login"),
            Columna("", clase="col-acciones"),
        ],
        buscar_en=["username", "first_name", "last_name", "email"],
        orden_por_omision="username",
    )

    contexto = {
        **marco(request),
        "tabla": tabla,
        "buscador": "Usuario, nombre o correo",
        "cuantos": Persona.objects.count(),
        "sin_rol": Persona.objects.filter(roles__isnull=True).count(),
        "cuantos_roles": Rol.objects.filter(activo=True).count(),
    }
    return render(request, "seguridad/usuarios.html", contexto)


@login_required
@requiere_lectura("usuarios")
def usuario(request: HttpRequest, pk: int) -> HttpResponse:
    """Los roles de una persona y lo que puede con ellos, hoy."""
    Persona = get_user_model()
    persona = get_object_or_404(Persona, pk=pk)
    if request.method == "POST":
        exigir_escritura(request, "usuarios")
        formulario = FormularioRoles(request.POST, persona=persona)
        if formulario.is_valid():
            persona.roles.set(formulario.cleaned_data["roles"])
            cuantos = len(formulario.cleaned_data["roles"])
            messages.success(request, f"Roles de «{persona}» actualizados: {cuantos}.")
            return redirect("seguridad:usuarios")
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioRoles(persona=persona)

    quien = permisos_de(persona)
    activas = registro.todas(solo_activas=True)
    marcados = _marcados(formulario, request, persona)
    contexto = {
        **marco(request),
        "formulario": formulario,
        "persona": persona,
        "es_uno_mismo": persona.pk == request.user.pk,
        "quien": quien,
        "grupos": _niveles_por_apartado(quien),
        "abierto": quien.es_abierto,
        "roles": [
            {
                "rol": rol,
                "marcado": rol.pk in marcados,
                "opciones": getattr(rol, "cuantas_opciones", 0),
                "escritura": getattr(rol, "con_escritura", 0),
            }
            for rol in formulario.fields["roles"].queryset
        ],
        "puede_ver": sum(1 for opcion in activas if quien.puede_leer(opcion.clave)),
        "puede_escribir": sum(
            1 for opcion in activas if quien.puede_escribir(opcion.clave)
        ),
        "opciones_totales": len(registro.todas()),
    }
    return render(request, "seguridad/usuario.html", contexto)


# ------------------------------------------------------------------ opciones


def _roles_que_la_tienen():
    """Cuántos roles tienen marcada cada opción (para la tabla)."""
    return (
        Permiso.objects.filter(opcion=OuterRef("clave"))
        .order_by()
        .values("opcion")
        .annotate(cuantos=Count("pk"))
        .values("cuantos")
    )


@login_required
@requiere_lectura("ajustes")
def ajustes(request: HttpRequest) -> HttpResponse:
    """La configuración de la aplicación, sin pasar por el admin.

    Son los ajustes que antes vivían en ``settings.py``: el modo de los permisos, el
    bloqueo de la pantalla, el ambiente del SRI, si se descuenta el inventario o si
    se contabiliza al autorizar. Cada paquete los declara y aquí se cambian.
    """
    from personalize_options import ajustes as registro
    from personalize_options.models import Ajuste

    if request.method == "POST":
        exigir_escritura(request, "ajustes")
        cambiados = 0
        for clave in request.POST.getlist("clave"):
            objeto = Ajuste.objects.filter(clave=clave, editable=True).first()
            if objeto is None:
                continue
            nuevo = (request.POST.get(f"valor-{clave}") or "").strip()
            if objeto.tipo == Ajuste.Tipo.BOOLEANO:
                nuevo = "si" if request.POST.get(f"valor-{clave}") else "no"
            if nuevo != objeto.valor:
                objeto.valor = nuevo
                objeto.save(update_fields=["valor", "actualizado"])
                cambiados += 1
        registro._leidos_de_la_base.cache_clear()
        if cambiados:
            messages.success(
                request,
                f"Se guardaron {cambiados} ajuste{'s' if cambiados != 1 else ''}.",
            )
        else:
            messages.info(request, "No había nada que cambiar.")
        return redirect("seguridad:ajustes")

    # Los declarados por los paquetes, y los que estén en la base aunque ya no se
    # declaren (para no esconder nada).
    declarados = {ajuste.clave for ajuste in registro.todos()}
    for fila in Ajuste.objects.all():
        if fila.clave not in declarados:
            registro.registrar(
                registro.AjusteDeSerie(
                    fila.clave,
                    fila.valor,
                    tipo=fila.tipo,
                    grupo=fila.grupo or "General",
                    descripcion=fila.descripcion,
                    orden=fila.orden,
                    editable=fila.editable,
                    origen=fila.origen or "la base",
                )
            )
    guardados = {fila.clave: fila for fila in Ajuste.objects.all()}

    # Se agrupa por quien los declara y, dentro, por grupo: los de
    # ``personalize_options`` aparte de los de ``factec`` y de los de cada
    # aplicación del proyecto.
    bloques: List[Dict[str, Any]] = []
    for declarado in registro.todos():
        fila = guardados.get(declarado.clave)
        if fila is None:
            continue
        nombre = fila.grupo or declarado.grupo or "General"
        origen = fila.origen or declarado.origen or "personalize_options"
        if not bloques or (bloques[-1]["origen"], bloques[-1]["nombre"]) != (
            origen,
            nombre,
        ):
            bloques.append({"origen": origen, "nombre": nombre, "ajustes": []})
        bloques[-1]["ajustes"].append(
            {
                "clave": fila.clave,
                "valor": fila.valor,
                "tipo": fila.tipo,
                "descripcion": fila.descripcion,
                "editable": fila.editable,
                "si": fila.como_valor is True,
            }
        )

    return render(
        request,
        "seguridad/ajustes.html",
        {
            **marco(request),
            "bloques": bloques,
            "cuantos": len(guardados),
            "origenes": sorted({bloque["origen"] for bloque in bloques}),
        },
    )


@login_required
@requiere_lectura("opciones")
def opciones(request: HttpRequest) -> HttpResponse:
    """El catálogo de opciones: las pantallas que se pueden permitir o negar."""
    listado = Opcion.objects.annotate(cuantos_roles=Subquery(_roles_que_la_tienen()))
    tabla = Tabla(
        request,
        listado,
        columnas=[
            Columna("Apartado", "grupo"),
            Columna("Opción", "nombre"),
            Columna("Clave", "clave"),
            Columna("En el menú", "url"),
            Columna("Roles", "cuantos_roles", clase="col-num"),
            Columna("Orden", clase="col-orden"),
            Columna("", clase="col-acciones"),
        ],
        buscar_en=["clave", "nombre", "grupo", "url"],
        orden_por_omision="orden",
    )

    contexto = {
        **marco(request),
        "tabla": tabla,
        "buscador": "Nombre, clave o apartado",
        "cuantas": Opcion.objects.count(),
        "cuantas_activas": Opcion.objects.filter(activo=True).count(),
        "grupos": [grupo for grupo, _ in registro.grupos()],
    }
    return render(request, "seguridad/opciones.html", contexto)


@login_required
@requiere_lectura("opciones")
def ordenar_menu(request: HttpRequest) -> HttpResponse:
    """El orden del menú, para cambiarlo arrastrando y no con números."""
    opciones_menu = Opcion.objects.filter(activo=True, en_menu=True).order_by(
        "orden", "nombre"
    )
    grupos: Dict[str, List[Opcion]] = {}
    for opcion_menu in opciones_menu:
        grupos.setdefault(opcion_menu.grupo, []).append(opcion_menu)

    return render(
        request,
        "seguridad/ordenar_menu.html",
        {
            **marco(request),
            "grupos": [{"nombre": nombre, "opciones": lista} for nombre, lista in grupos.items()],
            "cuantas": opciones_menu.count(),
        },
    )


@login_required
@require_POST
@requiere_escritura("opciones")
def guardar_orden_menu(request: HttpRequest) -> JsonResponse:
    """Guarda el orden que dejó el arrastre: una lista plana de opciones."""
    if request.content_type == "application/json":
        try:
            ids = json.loads(request.body or "[]")
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Orden inválido."}, status=400)
    else:
        ids = request.POST.getlist("opciones")

    limpios: List[int] = []
    for valor in ids:
        try:
            limpios.append(int(valor))
        except (TypeError, ValueError):
            continue

    if not limpios:
        return JsonResponse({"ok": False, "error": "No llegó ningún cambio."}, status=400)

    existentes = Opcion.objects.in_bulk(limpios)
    with transaction.atomic():
        for posicion, pk in enumerate(limpios, start=1):
            if pk in existentes:
                Opcion.objects.filter(pk=pk).update(orden=posicion)

    return JsonResponse({"ok": True, "cuantas": len(limpios)})


@login_required
@require_POST
@requiere_escritura("opciones")
def mover_opcion(request: HttpRequest, pk: int, sentido: str) -> HttpResponse:
    """Sube o baja una opción un puesto dentro de su apartado.

    Es un solo toque, sin arrastrar ni escribir números: se cambia el puesto con
    la de al lado y el apartado se renumera 1..n para que el orden quede limpio.
    Si ya está la primera (o la última), no pasa nada.
    """
    objeto = get_object_or_404(Opcion, pk=pk)
    companeras = list(
        Opcion.objects.filter(grupo=objeto.grupo).order_by("orden", "nombre", "pk")
    )

    try:
        puesto = next(indice for indice, fila in enumerate(companeras) if fila.pk == objeto.pk)
    except StopIteration:  # pragma: no cover - la opción acaba de estar en la lista
        return redirect("seguridad:ordenar_menu")

    vecina = puesto - 1 if sentido == "arriba" else puesto + 1
    if 0 <= vecina < len(companeras):
        companeras[puesto], companeras[vecina] = companeras[vecina], companeras[puesto]
        with transaction.atomic():
            for posicion, fila in enumerate(companeras, start=1):
                if fila.orden != posicion:
                    Opcion.objects.filter(pk=fila.pk).update(orden=posicion)
        messages.success(
            request,
            f"«{objeto.nombre}» pasó al puesto {vecina + 1} de «{objeto.grupo}».",
        )
    else:
        messages.info(
            request,
            "Ya está en el extremo de su apartado."
            if sentido in {"arriba", "abajo"}
            else "No hay a dónde moverla.",
        )

    # Se vuelve a donde se estaba: la lista lleva sus filtros en la dirección.
    volver = request.POST.get("volver", "")
    if volver and url_has_allowed_host_and_scheme(
        volver, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(volver)
    return redirect("seguridad:ordenar_menu")


@login_required
@requiere_lectura("opciones")
def opcion(request: HttpRequest, pk: Optional[int] = None) -> HttpResponse:
    """Crear una opción nueva o corregir una de las que hay."""
    objeto = get_object_or_404(Opcion, pk=pk) if pk else Opcion()
    clave_antes = objeto.clave if objeto.pk else ""

    if request.method == "POST":
        exigir_escritura(request, "opciones")
        formulario = FormularioOpcion(request.POST, instance=objeto)
        if formulario.is_valid():
            guardada = formulario.save()
            aviso = f"Opción «{guardada.nombre}» guardada."
            if clave_antes and clave_antes != guardada.clave:
                aviso += " Los permisos que la nombraban se movieron con ella."
            messages.success(request, aviso)
            return redirect("seguridad:opciones")
        messages.error(request, "Revise lo que está marcado en rojo.")

    contexto = {
        **marco(request),
        "formulario": formulario if request.method == "POST" else FormularioOpcion(instance=objeto),
        "opcion": objeto,
        "es_nueva": pk is None,
        "roles_que_la_tienen": (
            Rol.objects.filter(permisos__opcion=objeto.clave).distinct() if objeto.pk else []
        ),
    }
    return render(request, "seguridad/opcion.html", contexto)


@login_required
@require_POST
@requiere_escritura("opciones")
def accion_opcion(request: HttpRequest, pk: int, que: str) -> HttpResponse:
    """Apagar una opción, volver a encenderla o quitarla del catálogo."""
    objeto = get_object_or_404(Opcion, pk=pk)
    nombre = objeto.nombre

    if que == "activar":
        objeto.activo = True
        objeto.save()
        messages.success(request, f"Opción «{nombre}» activada.")
    elif que == "desactivar":
        objeto.activo = False
        objeto.save()
        messages.info(
            request,
            f"Opción «{nombre}» desactivada: deja de salir en el menú y en el "
            "asistente, y sus permisos dejan de contar.",
        )
    elif que == "eliminar":
        cuantos = Permiso.objects.filter(opcion=objeto.clave).count()
        objeto.delete()
        aviso = f"Opción «{nombre}» eliminada."
        if cuantos:
            aviso += f" Se quitaron {cuantos} permiso(s) que la nombraban."
        messages.success(request, aviso)
    else:
        raise Http404(f"«{que}» no es algo que se le pueda hacer a una opción.")

    return redirect("seguridad:opciones")


@login_required
@requiere_lectura("usuarios")
def usuario_nuevo(request: HttpRequest) -> HttpResponse:
    """Dar de alta a una persona desde la aplicación, sin pasar por el admin.

    Se piden sus datos, su clave —dos veces— y los roles que va a llevar. La cuenta
    queda lista para entrar en el momento: no hay que activar nada después.
    """
    Persona = get_user_model()
    if request.method == "POST":
        exigir_escritura(request, "usuarios")
        # La casilla de «puede entrar» viene marcada: una cuenta nueva nace activa
        # salvo que se desmarque a propósito.
        datos = request.POST.copy()
        datos.setdefault("is_active", "on")
        formulario = FormularioUsuario(datos, persona=Persona())
        if formulario.is_valid():
            persona = formulario.save()
            messages.success(
                request,
                f"«{persona.get_full_name() or persona.username}» quedó creado y ya puede entrar.",
            )
            return redirect("seguridad:usuario", pk=persona.pk)
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioUsuario(persona=Persona())

    return render(
        request,
        "seguridad/usuario_nuevo.html",
        {
            **marco(request),
            "formulario": formulario,
            "roles": formulario.fields["roles"].queryset,
        },
    )


@login_required
@requiere_lectura("usuarios")
def usuario_datos(request: HttpRequest, pk: int) -> HttpResponse:
    """Los datos y la clave de una persona (los roles se cambian en su pantalla)."""
    Persona = get_user_model()
    persona = get_object_or_404(Persona, pk=pk)
    # La cuenta de servicio del sistema (el superusuario de Django) no se toca
    # desde aquí: quien lleva «usuarios» podría ponerle su clave y quedarse con
    # el admin entero.
    if persona.is_superuser and not request.user.is_superuser:
        raise PermissionDenied(
            "La cuenta de administración del sistema solo la puede cambiar otro "
            "superusuario, desde el admin."
        )
    if request.method == "POST":
        exigir_escritura(request, "usuarios")
        formulario = FormularioUsuario(request.POST, instance=persona, persona=persona)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Los datos de la cuenta quedaron guardados.")
            return redirect("seguridad:usuarios")
        messages.error(request, "Revise lo que está marcado en rojo.")
    else:
        formulario = FormularioUsuario(instance=persona, persona=persona)

    return render(
        request,
        "seguridad/usuario_datos.html",
        {
            **marco(request),
            "formulario": formulario,
            "persona": persona,
            "es_uno_mismo": persona.pk == request.user.pk,
            "roles": formulario.fields["roles"].queryset,
        },
    )
