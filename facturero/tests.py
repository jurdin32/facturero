"""Pruebas del bloqueo de la pantalla y de la pantalla de entrar.

El bloqueo tiene que ser de verdad: si la sesión está bloqueada, el servidor no
entrega la página que se pide, entregue la que entregue. Eso es lo que se
comprueba aquí, además de que la clave se valide contra el mismo usuario.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from personalize_options.models import Nivel, Permiso, Rol

from . import sesion

CLAVE = "una-clave-larga-123"


class PruebasDelBloqueo(TestCase):
    def setUp(self) -> None:
        self.usuario = User.objects.create_user("pruebas", password=CLAVE)
        self.client.force_login(self.usuario)
        self.sesion = self.client.session

    def _bloquear(self) -> None:
        self.sesion[sesion.BLOQUEADA] = True
        self.sesion.save()

    def _vieja(self, minutos: int) -> None:
        self.sesion[sesion.ULTIMA] = (timezone.now() - timedelta(minutes=minutos)).isoformat()
        self.sesion.save()

    # ------------------------------------------------------------ el bloqueo

    def test_una_sesion_bloqueada_no_entrega_la_pagina_que_se_pide(self) -> None:
        self._bloquear()

        respuesta = self.client.get("/")

        self.assertEqual(respuesta.status_code, 423)
        pagina = respuesta.content.decode()
        self.assertIn("Aplicación bloqueada", pagina)
        self.assertIn(self.usuario.get_username(), pagina)
        self.assertIn('name="password"', pagina)

    def test_la_inactividad_bloquea_la_sesion_sola(self) -> None:
        self._vieja(sesion.minutos_de_bloqueo() + 1)

        respuesta = self.client.get("/")

        self.assertEqual(respuesta.status_code, 423)
        self.assertTrue(self.client.session.get(sesion.BLOQUEADA))

    def test_mientras_se_usa_no_se_bloquea(self) -> None:
        self._vieja(1)

        respuesta = self.client.get("/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(self.client.session.get(sesion.BLOQUEADA))

    @override_settings(BLOQUEO_INACTIVIDAD_MINUTOS=0)
    def test_sin_tiempo_de_bloqueo_no_bloquea_nunca(self) -> None:
        self._vieja(60 * 24)
        self._bloquear()

        respuesta = self.client.get("/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotEqual(respuesta.status_code, 423)

    def test_las_peticiones_de_fondo_reciben_un_aviso_y_no_la_pantalla(self) -> None:
        self._bloquear()

        respuesta = self.client.get("/", headers={"x-requested-with": "XMLHttpRequest"})

        self.assertEqual(respuesta.status_code, 423)
        self.assertTrue(respuesta.json()["bloqueada"])

    def test_lo_estatico_y_el_login_quedan_fuera_del_bloqueo(self) -> None:
        self._bloquear()

        # Los estáticos se sirven fuera del bloqueo (si no, la propia pantalla no
        # cargaría sus estilos) y el login tampoco se bloquea.
        self.assertTrue(sesion._exenta("/static/css/interfaz.css"))  # noqa: SLF001
        self.assertTrue(sesion._exenta("/entrar/"))  # noqa: SLF001
        login = self.client.get("/entrar/")
        self.assertNotEqual(login.status_code, 423)

    def test_el_boton_de_la_barra_bloquea_la_pantalla(self) -> None:
        respuesta = self.client.post("/bloquear/", {"next": "/inventario/"})

        self.assertEqual(respuesta.status_code, 423)
        self.assertTrue(self.client.session.get(sesion.BLOQUEADA))
        self.assertIn('value="/inventario/"', respuesta.content.decode())

    # ---------------------------------------------------------- el desbloqueo

    def test_desbloquear_con_la_clave_buena_deja_pasar(self) -> None:
        self._bloquear()

        respuesta = self.client.post(
            "/desbloquear/",
            {"password": CLAVE, "next": "/inventario/"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["siguiente"], "/inventario/")
        self.assertFalse(self.client.session.get(sesion.BLOQUEADA))
        self.assertEqual(self.client.get("/inventario/").status_code, 200)

    def test_desbloquear_con_la_clave_mala_avisa_y_no_deja_pasar(self) -> None:
        self._bloquear()

        respuesta = self.client.post(
            "/desbloquear/",
            {"password": "no-es-esa"},
            headers={"x-requested-with": "XMLHttpRequest"},
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("clave", respuesta.json()["error"].lower())
        self.assertTrue(self.client.session.get(sesion.BLOQUEADA))
        self.assertEqual(self.client.get("/").status_code, 423)

    def test_sin_javascript_el_desbloqueo_redirige(self) -> None:
        self._bloquear()

        respuesta = self.client.post("/desbloquear/", {"password": CLAVE, "next": "/inventario/"})

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.headers["Location"], "/inventario/")


class PruebasDeLaPantallaDeEntrar(TestCase):
    def test_la_pantalla_de_entrar_trae_su_diseno(self) -> None:
        respuesta = self.client.get("/entrar/")

        self.assertEqual(respuesta.status_code, 200)
        pagina = respuesta.content.decode()
        self.assertIn("entrar-fondo", pagina)          # el fondo abstracto
        self.assertIn("entrar-avatar", pagina)         # el círculo con la silueta
        self.assertIn("Opciones de inicio de sesión", pagina)

    def test_el_fondo_del_login_es_un_archivo_de_verdad(self) -> None:
        from django.contrib.staticfiles import finders

        self.assertIsNotNone(finders.find("img/fondo-entrar.svg"))
        self.assertIsNotNone(finders.find("js/bloqueo.js"))
        self.assertIsNotNone(finders.find("js/entrar.js"))

    def test_el_boton_de_entrar_es_la_flecha_del_campo(self) -> None:
        pagina = self.client.get("/entrar/").content.decode()

        self.assertIn('name="username"', pagina)
        self.assertIn('name="password"', pagina)
        self.assertIn("entrar-flecha", pagina)


class PruebasDelMenu(TestCase):
    """El menú: los apartados plegables y el de la pantalla en la que se está.

    El menú se quedaba sin alto según se añadían opciones, así que ahora va en
    apartados que se abren y se cierran solos (``<details>``, sin JavaScript) y
    viene desplegado el que toca. Esto lo vigila.
    """

    #: Cada apartado, con su título y si viene desplegado.
    _APARTADO = re.compile(
        r"<details(?P<abierto> open)?>\s*<summary>.*?"
        r'<span class="caption">(?P<nombre>[^<]+)</span>',
        re.S,
    )

    def setUp(self) -> None:
        User.objects.create_user("quien-mira-el-menu", password="clave-de-pruebas")
        self.client.force_login(User.objects.get(username="quien-mira-el-menu"))

    def _pagina(self, ruta: str) -> str:
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200, ruta)
        return respuesta.content.decode()

    def _apartados(self, pagina: str) -> dict[str, bool]:
        return {
            hallado.group("nombre"): bool(hallado.group("abierto"))
            for hallado in self._APARTADO.finditer(pagina)
        }

    def test_los_apartados_son_plegables_y_llevan_sus_opciones(self) -> None:
        pagina = self._pagina("/")

        # El menú se pinta dos veces: el lateral y el panel que abre el móvil.
        menus = pagina.split('class="sidenav"')[1:]
        self.assertEqual(len(menus), 2)
        for menu in menus:
            self.assertEqual(menu.count('class="menu-grupo"'), 8)
            self.assertEqual(menu.count('class="menu-submenu"'), 8)
        for etiqueta in (
            "Nueva factura", "Facturas emitidas", "Notas de crédito", "Notas de débito",
            "Liquidaciones de compra", "Guías de remisión", "Retenciones",
            "Productos y servicios", "Clientes", "Conductores", "Vehículos", "Inventario",
            "Configuración del SRI", "Roles y permisos", "Usuarios y sus roles", "Administración",
            "Caja del turno", "Plan de cuentas", "Asientos contables",
            "Reportes y estadísticas", "Manual del sistema",
        ):
            self.assertIn(etiqueta, pagina, etiqueta)

    def test_en_el_tablero_no_hay_ningun_apartado_desplegado(self) -> None:
        self.assertEqual(
            self._apartados(self._pagina("/")),
            {
                "Facturar": False,
                "Comprobantes": False,
                "Catálogo": False,
                "Sistema": False,
                "Caja": False,
                "Contabilidad": False,
                "Reportes": False,
                "Ayuda": False,
            },
        )

    def test_el_apartado_de_la_pantalla_en_la_que_se_esta_viene_desplegado(self) -> None:
        for ruta, apartado in (
            ("/facturas/", "Facturar"),
            ("/comprobantes/guias-remision/", "Comprobantes"),
            ("/catalogos/conductores/", "Catálogo"),
            ("/catalogos/vehiculos/", "Catálogo"),
            ("/inventario/", "Catálogo"),
            ("/configuracion/sri/", "Sistema"),
        ):
            with self.subTest(ruta=ruta):
                abiertos = self._apartados(self._pagina(ruta))
                self.assertEqual([nombre for nombre, abierto in abiertos.items() if abierto], [apartado])

    def test_la_opcion_de_la_pantalla_actual_va_marcada_dentro_de_su_apartado(self) -> None:
        pagina = self._pagina("/catalogos/conductores/")

        self.assertRegex(
            pagina, r'<li class="active"[^>]*>\s*<a href="/catalogos/conductores/"'
        )

    def test_el_menu_se_pinta_igual_en_el_lateral_y_en_el_panel_del_movil(self) -> None:
        pagina = self._pagina("/")

        # Dos veces: el lateral de escritorio y el panel que abre el botón del móvil.
        self.assertEqual(pagina.count('class="sidenav"'), 2)


class PruebasDelMenuConPermisos(TestCase):
    """El menú enseña solo lo que se puede ver.

    Los permisos los da el paquete ``personalize_options``: si una opción no se
    puede leer, su enlace no se pinta, y un apartado que se queda sin ninguna
    opción tampoco.
    """

    def setUp(self) -> None:
        self.usuario = User.objects.create_user("quien-mira-el-menu-con-permisos")
        self.client.force_login(self.usuario)

    def _con_rol(self, **niveles: str) -> None:
        rol = Rol.objects.create(nombre="Ventas")
        rol.usuarios.add(self.usuario)
        for opcion, nivel in niveles.items():
            Permiso.objects.create(rol=rol, opcion=opcion, nivel=nivel)

    def _menu(self, ruta: str = "/") -> str:
        """El menú del lateral (el del móvil es el mismo, pintado otra vez)."""
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200)
        pagina = respuesta.content.decode()
        return re.search(r'<ul class="sidenav"[^>]*>(.*?)</aside>', pagina, re.S).group(1)

    @override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True})
    def test_lo_que_no_se_puede_leer_no_se_enseña(self) -> None:
        self._con_rol(tablero=Nivel.LECTURA.value, clientes=Nivel.LECTURA.value)
        menu = self._menu()

        self.assertIn("Tablero", menu)
        self.assertIn("Clientes", menu)
        for etiqueta in (
            "Nueva factura", "Facturas emitidas", "Notas de crédito", "Guías de remisión",
            "Productos y servicios", "Conductores", "Vehículos", "Inventario",
            "Configuración del SRI", "Roles y permisos", "Usuarios y sus roles",
        ):
            self.assertNotIn(etiqueta, menu, etiqueta)

    @override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True})
    def test_un_apartado_sin_opciones_visibles_no_se_enseña(self) -> None:
        self._con_rol(tablero=Nivel.LECTURA.value, clientes=Nivel.LECTURA.value)
        menu = self._menu()

        # Solo queda el apartado del catálogo: los otros tres se caen enteros.
        self.assertEqual(menu.count('class="menu-grupo"'), 1)
        self.assertIn("Catálogo", menu)
        self.assertNotIn("Facturar", menu)
        self.assertNotIn("Comprobantes", menu)
        self.assertNotIn("Sistema", menu)

    @override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True})
    def test_con_escritura_se_enseña_igual_que_con_lectura(self) -> None:
        self._con_rol(tablero=Nivel.ESCRITURA.value, clientes=Nivel.ESCRITURA.value)
        menu = self._menu()

        self.assertIn("Tablero", menu)
        self.assertIn("Clientes", menu)

    @override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True})
    def test_las_pantallas_de_seguridad_salen_si_se_pueden_ver(self) -> None:
        self._con_rol(
            roles=Nivel.LECTURA.value,
            usuarios=Nivel.ESCRITURA.value,
            configuracion=Nivel.LECTURA.value,
        )

        # Sin el tablero no se puede mirar la portada: se pide el menú de una de sus
        # pantallas, que es el mismo lateral.
        menu = self._menu("/seguridad/")

        self.assertIn("Roles y permisos", menu)
        self.assertIn("Usuarios y sus roles", menu)
        self.assertIn("/seguridad/", menu)

    @override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True})
    def test_el_apartado_de_sistema_viene_desplegado_en_las_de_seguridad(self) -> None:
        self._con_rol(roles=Nivel.LECTURA.value, usuarios=Nivel.LECTURA.value)

        respuesta = self.client.get("/seguridad/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertRegex(
            respuesta.content.decode(), r"(?s)<details open>\s*<summary>.*?Sistema"
        )

    def test_en_modo_abierto_se_enseña_todo(self) -> None:
        menu = self._menu()

        self.assertEqual(menu.count('class="menu-grupo"'), 8)
        self.assertIn("Tablero", menu)
        self.assertIn("Configuración del SRI", menu)
        self.assertIn("Plan de cuentas", menu)
        self.assertIn("Reportes y estadísticas", menu)
        self.assertIn("Manual del sistema", menu)


class PruebasDeLasTablasDeSeguridad(TestCase):
    """Las tablas del paquete de seguridad se ven en el admin del proyecto."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("quien-manda", "jefe@ejemplo.ec", "secreta-clave")
        self.client.force_login(self.jefe)

    def test_el_admin_enseña_las_tablas_de_roles_y_permisos(self) -> None:
        pagina = self.client.get("/admin/").content.decode()

        self.assertIn("/admin/personalize_options/rol/", pagina)
        self.assertIn("/admin/personalize_options/permiso/", pagina)
