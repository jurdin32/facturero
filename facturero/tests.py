"""Pruebas del bloqueo de la pantalla y de la pantalla de entrar.

El bloqueo tiene que ser de verdad: si la sesión está bloqueada, el servidor no
entrega la página que se pide, entregue la que entregue. Eso es lo que se
comprueba aquí, además de que la clave se valide contra el mismo usuario.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path as Ruta

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

    def test_sin_tiempo_de_bloqueo_no_bloquea_nunca(self) -> None:
        from personalize_options import ajustes

        self._vieja(60 * 24)
        self._bloquear()

        with ajustes.usar(bloqueo_inactividad_minutos=0):
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
            self.assertEqual(menu.count('class="menu-grupo"'), 9)
            self.assertEqual(menu.count('class="menu-submenu"'), 9)
        for etiqueta in (
            "Nueva factura", "Facturas emitidas", "Notas de crédito", "Notas de débito",
            "Liquidaciones de compra", "Guías de remisión", "Retenciones",
            "Productos y servicios", "Clientes", "Conductores", "Vehículos", "Inventario",
            "Configuración del SRI", "Roles y permisos", "Usuarios y sus roles", "Administración",
            "Caja del turno", "Revisión de caja", "Vales de caja",
            "Plan de cuentas", "Asientos contables",
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
                "Supervisión": False,
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

        self.assertEqual(menu.count('class="menu-grupo"'), 9)
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


class PruebasDeLosAjustes(TestCase):
    """La configuración de la aplicación vive en la base, no en settings.py."""

    def test_los_ajustes_de_cada_app_quedan_sembrados_al_migrar(self) -> None:
        from personalize_options.models import Ajuste

        claves = set(Ajuste.objects.values_list("clave", flat=True))

        for clave in (
            "modo",
            "superusuarios_todo",
            "bloqueo_inactividad_minutos",
            "inventario_descontar_al_facturar",
        ):
            self.assertIn(clave, claves, clave)

    def test_los_ajustes_de_la_contabilidad_van_en_la_tabla_de_su_paquete(self) -> None:
        # Igual que el SRI: cada paquete con su tabla.
        from conta_ec.django.models import AjusteDeLaContabilidad
        from personalize_options.models import Ajuste

        suyos = set(AjusteDeLaContabilidad.objects.values_list("clave", flat=True))
        self.assertIn("contabilidad_contabilizar_al_autorizar", suyos)
        self.assertIn("contabilidad_periodo_automatico", suyos)
        self.assertEqual(
            list(
                Ajuste.objects.filter(clave__startswith="contabilidad_").values_list(
                    "clave", flat=True
                )
            ),
            [],
        )

    def test_los_ajustes_del_sri_van_en_la_tabla_de_su_paquete(self) -> None:
        # Los paquetes son independientes: `factec` guarda lo suyo en su tabla y
        # no en la del proyecto.
        from factec.django.models import AjusteDelSri
        from personalize_options.models import Ajuste

        suyos = set(AjusteDelSri.objects.values_list("clave", flat=True))
        for clave in ("sri_ambiente", "sri_guardar_xml", "sri_guardar_archivos"):
            self.assertIn(clave, suyos, clave)

        self.assertEqual(
            list(Ajuste.objects.filter(clave__startswith="sri_").values_list("clave", flat=True)),
            [],
        )

    def test_el_valor_sale_de_la_base(self) -> None:
        from personalize_options import ajustes

        self.assertEqual(ajustes.entero("bloqueo_inactividad_minutos"), 15)

        ajustes.poner("bloqueo_inactividad_minutos", 45)

        self.assertEqual(ajustes.entero("bloqueo_inactividad_minutos"), 45)

    def test_un_booleano_se_lee_como_si_o_no(self) -> None:
        from personalize_options import ajustes

        self.assertTrue(ajustes.booleano("inventario_descontar_al_facturar"))

        ajustes.poner("inventario_descontar_al_facturar", False)

        self.assertFalse(ajustes.booleano("inventario_descontar_al_facturar"))

    def test_se_puede_fijar_un_ajuste_sin_tocar_la_base(self) -> None:
        from personalize_options import ajustes

        with ajustes.usar(bloqueo_inactividad_minutos=0):
            self.assertEqual(ajustes.entero("bloqueo_inactividad_minutos"), 0)

        self.assertEqual(ajustes.entero("bloqueo_inactividad_minutos"), 15)

    def test_settings_py_no_lleva_configuracion_de_la_aplicacion(self) -> None:
        from pathlib import Path as Ruta

        from django.conf import settings

        ruta = Ruta(settings.BASE_DIR) / "facturero" / "settings.py"
        texto = ruta.read_text(encoding="utf-8")

        for nombre in (
            "PERSONALIZE_OPTIONS",
            "FACTURACION_ELECTRONICA",
            "INVENTARIO_DESCONTAR_AL_FACTURAR",
            "CONTABILIDAD_CONTABILIZAR_AL_AUTORIZAR",
            "BLOQUEO_INACTIVIDAD_MINUTOS",
            "CELERY_BROKER_URL",
        ):
            self.assertNotIn(nombre + " =", texto, nombre)


class PruebasDelAdminDeLaSeguridad(TestCase):
    """Las pantallas del admin del paquete abren y cuentan bien."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        self.jefe = get_user_model().objects.create_superuser(
            "admin-ajustes", "admin@ejemplo.ec", "clave-larga-123"
        )
        self.client.force_login(self.jefe)

    def test_las_pantallas_del_paquete_abren(self) -> None:
        for url in (
            "/admin/personalize_options/opcion/",
            "/admin/personalize_options/ajuste/",
            "/admin/personalize_options/rol/",
            "/admin/personalize_options/categoria/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_la_columna_de_roles_se_puede_ordenar(self) -> None:
        # El permiso guarda la clave de la opción, no una foránea: el conteo va
        # con una subconsulta y el orden por esa columna tiene que resolver.
        self.assertEqual(self.client.get("/admin/personalize_options/opcion/?o=1").status_code, 200)
        self.assertEqual(self.client.get("/admin/personalize_options/opcion/?o=-1").status_code, 200)

    def test_los_ajustes_se_editan(self) -> None:
        from personalize_options.models import Ajuste

        ajuste = Ajuste.objects.get(clave="bloqueo_inactividad_minutos")
        respuesta = self.client.post(
            f"/admin/personalize_options/ajuste/{ajuste.pk}/change/",
            {"valor": "30"},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        ajuste.refresh_from_db()
        self.assertEqual(ajuste.valor, "30")

    def test_la_clave_de_un_ajuste_no_se_puede_renombrar(self) -> None:
        # La clave es la que lee el código: en el admin sólo se cambia el valor.
        from personalize_options.models import Ajuste

        ajuste = Ajuste.objects.get(clave="bloqueo_inactividad_minutos")
        formulario = self.client.get(
            f"/admin/personalize_options/ajuste/{ajuste.pk}/change/"
        ).content.decode()

        self.assertNotIn('name="clave"', formulario)
        self.assertIn('name="valor"', formulario)

        # Aunque se mande otra clave, se ignora.
        self.client.post(
            f"/admin/personalize_options/ajuste/{ajuste.pk}/change/",
            {"clave": "otra_cosa", "valor": "20"},
            follow=True,
        )
        self.assertTrue(Ajuste.objects.filter(clave="bloqueo_inactividad_minutos").exists())
        self.assertFalse(Ajuste.objects.filter(clave="otra_cosa").exists())

    def test_cada_ajuste_dice_de_que_paquete_viene(self) -> None:
        from personalize_options.models import Ajuste

        origenes = dict(Ajuste.objects.values_list("clave", "origen"))

        self.assertEqual(origenes["modo"], "personalize_options")
        self.assertEqual(origenes["inventario_descontar_al_facturar"], "inventario")
        self.assertEqual(origenes["bloqueo_inactividad_minutos"], "seguridad")
        # Ninguno se queda sin dueño.
        self.assertNotIn("", origenes.values())

    def test_un_ajuste_que_ya_existe_conserva_su_valor_al_migrar(self) -> None:
        from personalize_options import ajustes as registro
        from personalize_options.models import Ajuste

        Ajuste.objects.filter(clave="bloqueo_inactividad_minutos").update(valor="45")
        registro.sembrar()

        fila = Ajuste.objects.get(clave="bloqueo_inactividad_minutos")
        self.assertEqual(fila.valor, "45")
        self.assertEqual(fila.origen, "seguridad")


class PruebasSinArchivosDeEntorno(TestCase):
    """La configuración está en la base: no hay `.env` en ninguna parte.

    Si alguien vuelve a meter un archivo de entorno —o el código empieza a leer
    variables—, esta prueba lo dice antes de que llegue al servidor.
    """

    def test_no_hay_archivos_de_entorno(self) -> None:
        from django.conf import settings

        base = Ruta(settings.BASE_DIR)
        encontrados = [
            str(ruta.relative_to(base))
            for ruta in base.rglob("*")
            if ruta.is_file()
            and ruta.name in {".env", "env.ejemplo"}
            and ".venv" not in ruta.parts
        ]
        self.assertEqual(encontrados, [])

    def test_los_servicios_no_cargan_ningun_entorno(self) -> None:
        from django.conf import settings

        base = Ruta(settings.BASE_DIR) / "deploy" / "systemd"
        for unidad in base.glob("*.service"):
            texto = unidad.read_text(encoding="utf-8")
            self.assertNotIn("EnvironmentFile", texto, unidad.name)
            self.assertNotIn(".env", texto, unidad.name)

    def test_el_codigo_del_proyecto_no_lee_variables_de_entorno(self) -> None:
        from django.conf import settings

        base = Ruta(settings.BASE_DIR)
        for archivo in base.rglob("*.py"):
            if any(parte in {".venv", "migrations", "build", "dist"}
                   for parte in archivo.parts):
                continue
            if archivo == Ruta(__file__):
                continue
            texto = archivo.read_text(encoding="utf-8")
            self.assertNotRegex(
                texto,
                r"(?m)^[^#\n]*(?:os\.environ\s*\[|os\.getenv\()",
                archivo.as_posix(),
            )
            self.assertNotIn("from dotenv", texto, archivo.as_posix())

    def test_el_paquete_del_sri_no_lee_variables_de_entorno(self) -> None:
        import factec.django.conf as conf

        ruta = Ruta(conf.__file__)
        texto = ruta.read_text(encoding="utf-8")
        self.assertNotIn("os.environ", texto)
        self.assertNotIn("getenv", texto)
