"""Pruebas de las pantallas de la seguridad: listas, asistente y usuarios.

Se comprueba lo que ve quien las usa: que las listas busquen, ordenen y paginen, que
el asistente guarde el rol y sus permisos con casillas, que a la gente se le den los
roles, y que las pantallas mismas estén protegidas por el paquete.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from personalize_options.models import Nivel, Opcion, Permiso, Rol
from personalize_options.opciones import de, todas

#: La aplicación con los permisos mandando (que es como estará en producción).
CERRADO = {"MODO": "cerrado", "SUPERUSUARIOS_TODO": True}

#: La aplicación como está ahora, sin obligar a tener rol.
ABIERTO = {"MODO": "abierto", "SUPERUSUARIOS_TODO": True}


def _texto(pagina: str) -> str:
    """El texto de una página, sin etiquetas ni saltos de línea, para comparar."""
    limpio = pagina.replace("<strong>", " ").replace("</strong>", " ").replace("</span>", " ")
    return " ".join(limpio.split())


def _rol_con(nombre: str, usuario: User, **niveles: str) -> Rol:
    """Un rol activo para ese usuario, con las opciones que se indiquen."""
    rol = Rol.objects.create(nombre=nombre)
    rol.usuarios.add(usuario)
    for opcion, nivel in niveles.items():
        Permiso.objects.create(rol=rol, opcion=opcion, nivel=nivel)
    return rol


class PruebasDeLaListaDeRoles(TestCase):
    """La tabla de roles: buscador, orden y paginación."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("jefe", "jefe@ejemplo.ec", "clave-larga-123")
        self.client.force_login(self.jefe)

    def test_la_lista_enseña_cada_rol_con_lo_que_da(self) -> None:
        _rol_con(
            "Ventas", self.jefe, clientes=Nivel.ESCRITURA.value, tablero=Nivel.LECTURA.value
        )

        pagina = self.client.get("/seguridad/").content.decode()

        self.assertIn("Ventas", pagina)
        self.assertIn("Activo", pagina)
        self.assertIn(f"2 de {len(todas(solo_activas=True))}", _texto(pagina))

    def test_se_puede_buscar(self) -> None:
        Rol.objects.create(nombre="Ventas")
        Rol.objects.create(nombre="Bodega")

        pagina = self.client.get("/seguridad/", {"q": "bode"}).content.decode()

        self.assertIn("Bodega", pagina)
        self.assertNotIn("Ventas", pagina)

    def test_se_puede_ordenar_pulsando_en_la_cabecera(self) -> None:
        Rol.objects.create(nombre="Ventas")
        Rol.objects.create(nombre="Bodega")

        pagina = self.client.get("/seguridad/", {"orden": "nombre", "dir": "desc"}).content.decode()

        self.assertLess(pagina.index("Ventas"), pagina.index("Bodega"))
        self.assertIn('orden-desc', pagina)

    def test_se_puede_cambiar_cuántas_filas_por_página(self) -> None:
        for numero in range(12):
            Rol.objects.create(nombre=f"Rol {numero:02d}")

        primera = self.client.get("/seguridad/", {"por_pagina": "10"}).content.decode()
        segunda = self.client.get(
            "/seguridad/", {"por_pagina": "10", "pagina": "2"}
        ).content.decode()

        self.assertIn("Mostrando 1 a 10 de 12", _texto(primera))
        self.assertIn("Mostrando 11 a 12 de 12", _texto(segunda))
        self.assertIn("pagina=2", primera)          # hay enlace a la segunda página

    def test_sin_roles_la_lista_invita_a_crear_el_primero(self) -> None:
        pagina = self.client.get("/seguridad/").content.decode()

        self.assertIn("Todavía no hay roles", pagina)
        self.assertIn("/seguridad/roles/nuevo/", pagina)


class PruebasDelAsistenteDelRol(TestCase):
    """El asistente: el rol, sus permisos con casillas y el resumen."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("jefe", "jefe@ejemplo.ec", "clave-larga-123")
        self.client.force_login(self.jefe)

    def test_el_primer_paso_pide_lo_del_rol(self) -> None:
        pagina = self.client.get("/seguridad/roles/nuevo/").content.decode()

        for campo in ("nombre", "descripcion", "activo", "usuarios"):
            self.assertIn(f'name="{campo}"', pagina, campo)
        self.assertIn("Paso 1 de 3", pagina)

    def test_el_primer_paso_guarda_el_rol_y_pasa_a_los_permisos(self) -> None:
        respuesta = self.client.post(
            "/seguridad/roles/nuevo/",
            {
                "nombre": "Facturador",
                "descripcion": "Los que facturan",
                "activo": "on",
                "usuarios": [str(self.jefe.pk)],
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        rol = Rol.objects.get(nombre="Facturador")
        self.assertEqual(respuesta["Location"], f"/seguridad/roles/{rol.pk}/?paso=2")
        self.assertEqual(list(rol.usuarios.all()), [self.jefe])

    def test_el_segundo_paso_trae_una_casilla_de_leer_y_otra_de_escribir_por_opción(self) -> None:
        rol = Rol.objects.create(nombre="Facturador")

        pagina = self.client.get(f"/seguridad/roles/{rol.pk}/", {"paso": "2"}).content.decode()

        for opcion in todas(solo_activas=True):
            self.assertIn(f'name="leer_{opcion.clave}"', pagina, opcion.clave)
            self.assertIn(f'name="escribir_{opcion.clave}"', pagina, opcion.clave)
        self.assertEqual(pagina.count('type="checkbox"'), len(todas(solo_activas=True)) * 2)

    def test_lo_que_se_marca_queda_guardado(self) -> None:
        rol = Rol.objects.create(nombre="Facturador")

        respuesta = self.client.post(
            f"/seguridad/roles/{rol.pk}/?paso=2",
            {
                "leer_tablero": "on",
                "leer_clientes": "on",
                "escribir_clientes": "on",
                "escribir_facturar": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], f"/seguridad/roles/{rol.pk}/?paso=3")
        self.assertEqual(
            rol.opciones,
            {
                "tablero": Nivel.LECTURA.value,
                "clientes": Nivel.ESCRITURA.value,
                # Marcar escribir ya incluye leer: no se modifica lo que no se ve.
                "facturar": Nivel.ESCRITURA.value,
            },
        )

    def test_desmarcar_una_opción_quita_el_permiso(self) -> None:
        rol = _rol_con("Facturador", self.jefe, clientes=Nivel.ESCRITURA.value)

        self.client.post(f"/seguridad/roles/{rol.pk}/?paso=2", {"leer_tablero": "on"})

        self.assertEqual(rol.opciones, {"tablero": Nivel.LECTURA.value})

    def test_el_segundo_paso_ya_viene_con_lo_marcado(self) -> None:
        rol = _rol_con("Facturador", self.jefe, clientes=Nivel.LECTURA.value)

        pagina = self.client.get(f"/seguridad/roles/{rol.pk}/", {"paso": "2"}).content.decode()

        casilla = pagina.split('name="leer_clientes"')[1][:60]
        self.assertIn("checked", casilla)
        self.assertNotIn("checked", pagina.split('name="escribir_clientes"')[1][:60])

    def test_el_resumen_enseña_lo_que_queda(self) -> None:
        rol = _rol_con(
            "Facturador", self.jefe, clientes=Nivel.ESCRITURA.value, tablero=Nivel.LECTURA.value
        )

        pagina = self.client.get(f"/seguridad/roles/{rol.pk}/", {"paso": "3"}).content.decode()

        self.assertIn("Lee y escribe", pagina)
        self.assertIn("Lee", pagina)
        self.assertIn("2", pagina)

    def test_los_permisos_de_un_rol_que_no_existe_no_se_pueden_marcar(self) -> None:
        pagina = self.client.get("/seguridad/roles/nuevo/", {"paso": "2"}).content.decode()

        self.assertIn("Paso 1 de 3", pagina)  # se queda en el primero

    def test_un_rol_se_apaga_se_enciende_y_se_borra(self) -> None:
        rol = Rol.objects.create(nombre="Bodega", activo=False)

        self.client.post(f"/seguridad/roles/{rol.pk}/activar/")
        rol.refresh_from_db()
        self.assertTrue(rol.activo)

        self.client.post(f"/seguridad/roles/{rol.pk}/desactivar/")
        rol.refresh_from_db()
        self.assertFalse(rol.activo)

        self.client.post(f"/seguridad/roles/{rol.pk}/eliminar/")
        self.assertFalse(Rol.objects.filter(nombre="Bodega").exists())

    def test_lo_que_no_es_una_acción_del_rol_da_404(self) -> None:
        rol = Rol.objects.create(nombre="Bodega")

        self.assertEqual(self.client.post(f"/seguridad/roles/{rol.pk}/bailar/").status_code, 404)


class PruebasDeLosUsuarios(TestCase):
    """La tabla de usuarios y los roles de cada uno."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("jefe", "jefe@ejemplo.ec", "clave-larga-123")
        self.client.force_login(self.jefe)
        self.quien = User.objects.create_user("vendedor", "vendedor@ejemplo.ec", password="x")

    def test_la_lista_enseña_los_roles_de_cada_uno(self) -> None:
        _rol_con("Ventas", self.quien, clientes=Nivel.LECTURA.value)

        pagina = self.client.get("/seguridad/usuarios/").content.decode()

        self.assertIn("vendedor", pagina)
        self.assertIn("vendedor@ejemplo.ec", pagina)
        self.assertIn("Ventas", pagina)

    def test_al_que_no_tiene_rol_se_le_dice(self) -> None:
        self.assertIn("Sin rol", self.client.get("/seguridad/usuarios/").content.decode())

    def test_se_puede_buscar_y_paginar(self) -> None:
        User.objects.create_user("otro-que-no-va")

        pagina = self.client.get("/seguridad/usuarios/", {"q": "vendedor"}).content.decode()

        self.assertIn("vendedor", pagina)
        self.assertNotIn("otro-que-no-va", pagina)
        self.assertIn("Mostrando 1 a 1 de 1", _texto(pagina))

    def test_darle_roles_a_alguien(self) -> None:
        ventas = Rol.objects.create(nombre="Ventas")
        bodega = Rol.objects.create(nombre="Bodega")

        respuesta = self.client.post(
            f"/seguridad/usuarios/{self.quien.pk}/",
            {"roles": [str(ventas.pk), str(bodega.pk)]},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            sorted(self.quien.roles.values_list("nombre", flat=True)), ["Bodega", "Ventas"]
        )

    def test_quitarle_todos_los_roles(self) -> None:
        _rol_con("Ventas", self.quien, clientes=Nivel.LECTURA.value)

        self.client.post(f"/seguridad/usuarios/{self.quien.pk}/", {})

        self.assertEqual(self.quien.roles.count(), 0)

    def test_la_pantalla_enseña_lo_que_puede_hoy(self) -> None:
        _rol_con(
            "Ventas", self.quien, clientes=Nivel.ESCRITURA.value, tablero=Nivel.LECTURA.value
        )

        pagina = self.client.get(f"/seguridad/usuarios/{self.quien.pk}/").content.decode()

        self.assertIn("Lee y escribe", pagina)
        self.assertIn(f"2 de {len(todas(solo_activas=True))}", _texto(pagina))

    def test_en_modo_abierto_avisa_de_que_puede_todo(self) -> None:
        # El aviso es para quien no tiene rol: con uno, manda el rol.
        self.quien.roles.clear()

        pagina = self.client.get(f"/seguridad/usuarios/{self.quien.pk}/").content.decode()

        self.assertIn("modo abierto", pagina)

    def test_a_la_hora_de_guardar_se_ve_lo_que_está_marcado(self) -> None:
        _rol_con("Ventas", self.quien, clientes=Nivel.LECTURA.value)

        pagina = self.client.get(f"/seguridad/usuarios/{self.quien.pk}/").content.decode()

        self.assertRegex(pagina, r'value="\d+" id="rol-\d+"\s+checked')


class PruebasDeLosPermisosDeLasPantallas(TestCase):
    """Las pantallas de la seguridad también están protegidas."""

    def setUp(self) -> None:
        self.quien = User.objects.create_user("vendedor", password="x")
        self.client.force_login(self.quien)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_sin_el_permiso_no_se_entra(self) -> None:
        self.assertEqual(self.client.get("/seguridad/").status_code, 403)
        self.assertEqual(self.client.get("/seguridad/usuarios/").status_code, 403)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_con_solo_lectura_se_mira_pero_no_se_guarda(self) -> None:
        rol = _rol_con(
            "Consulta", self.quien, roles=Nivel.LECTURA.value, usuarios=Nivel.LECTURA.value
        )
        suyo = Rol.objects.create(nombre="Otro")

        self.assertEqual(self.client.get("/seguridad/").status_code, 200)
        self.assertEqual(self.client.get("/seguridad/roles/nuevo/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/seguridad/roles/{suyo.pk}/", {"paso": "2"}).status_code, 200
        )

        # Al guardar sí hace falta escritura.
        self.assertEqual(
            self.client.post("/seguridad/roles/nuevo/", {"nombre": "Ventas"}).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                f"/seguridad/roles/{suyo.pk}/?paso=2", {"leer_tablero": "on"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"/seguridad/usuarios/{rol.pk}/", {"roles": []}).status_code, 403
        )

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_con_escritura_se_guarda(self) -> None:
        _rol_con("Oficina", self.quien, roles=Nivel.ESCRITURA.value)

        respuesta = self.client.post("/seguridad/roles/nuevo/", {"nombre": "Ventas", "activo": "on"})

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Rol.objects.filter(nombre="Ventas").exists())

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_las_dos_opciones_van_por_separado(self) -> None:
        _rol_con("Oficina", self.quien, roles=Nivel.ESCRITURA.value)

        self.assertEqual(self.client.get("/seguridad/").status_code, 200)
        self.assertEqual(self.client.get("/seguridad/usuarios/").status_code, 403)

    @override_settings(PERSONALIZE_OPTIONS=ABIERTO)
    def test_en_modo_abierto_se_entra_sin_roles(self) -> None:
        self.assertEqual(self.client.get("/seguridad/").status_code, 200)
        self.assertEqual(self.client.get("/seguridad/usuarios/").status_code, 200)


class PruebasDeLasOpciones(TestCase):
    """El catálogo de opciones: crear permisos nuevos desde la aplicación."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("jefe", "jefe@ejemplo.ec", "clave-larga-123")
        self.client.force_login(self.jefe)

    def _datos(self, **cambios) -> dict:
        datos = {
            "nombre": "Merma de bodega",
            "clave": "merma",
            "grupo": "Sistema",
            "orden": "99",
            "url": "/merma/",
            "icono": "storage",
            "en_menu": "on",
            "activo": "on",
        }
        datos.update(cambios)
        return datos

    def test_la_lista_enseña_las_opciones_y_en_cuántos_roles_están(self) -> None:
        _rol_con("Ventas", self.jefe, clientes=Nivel.LECTURA.value)

        pagina = self.client.get("/seguridad/opciones/").content.decode()

        self.assertIn("Clientes", pagina)
        self.assertIn("clientes", pagina)
        self.assertIn("Roles", pagina)

    def test_se_puede_buscar_y_ordenar(self) -> None:
        pagina = self.client.get(
            "/seguridad/opciones/", {"q": "cliente", "orden": "grupo", "dir": "desc"}
        ).content.decode()
        # Solo la tabla: el menú del lateral nombra todas las opciones.
        tabla = pagina.split('id="tabla-opciones"')[1].split("</table>")[0]

        self.assertIn("Clientes", tabla)
        self.assertNotIn("Guías de remisión", tabla)

    def test_crear_una_opción_nueva(self) -> None:
        respuesta = self.client.post("/seguridad/opciones/nueva/", self._datos())

        self.assertEqual(respuesta.status_code, 302)
        nueva = Opcion.objects.get(clave="merma")
        self.assertEqual((nueva.nombre, nueva.grupo, nueva.url), ("Merma de bodega", "Sistema", "/merma/"))
        # Y ya se puede marcar en un rol.
        self.assertIn("merma", {opcion.clave for opcion in todas(solo_activas=True)})

    def test_el_formulario_trae_el_orden_siguiente(self) -> None:
        pagina = self.client.get("/seguridad/opciones/nueva/").content.decode()

        self.assertIn('name="clave"', pagina)
        self.assertIn("apartados-conocidos", pagina)

    def test_corregir_una_opción(self) -> None:
        opcion = Opcion.objects.create(clave="merma", nombre="Merma", grupo="Sistema")

        self.client.post(
            f"/seguridad/opciones/{opcion.pk}/", self._datos(nombre="Reportes del mes", url="/mes/")
        )

        opcion.refresh_from_db()
        self.assertEqual((opcion.nombre, opcion.url), ("Reportes del mes", "/mes/"))

    def test_la_opción_nueva_sale_en_el_menú(self) -> None:
        Opcion.objects.create(
            clave="merma", nombre="Merma de bodega", grupo="Sistema",
            url="/merma/", icono="storage", orden=99,
        )

        pagina = self.client.get("/").content.decode()

        self.assertIn("Merma de bodega", pagina)
        self.assertIn('href="/merma/"', pagina)

    def test_una_opción_sin_dirección_no_sale_en_el_menú(self) -> None:
        Opcion.objects.create(clave="merma", nombre="Merma", grupo="Sistema", orden=99)

        self.assertNotIn("Merma", self.client.get("/").content.decode())

    def test_la_opción_nueva_sale_en_el_asistente_del_rol(self) -> None:
        Opcion.objects.create(clave="merma", nombre="Merma", grupo="Sistema", orden=99)
        rol = Rol.objects.create(nombre="Ventas")

        pagina = self.client.get(f"/seguridad/roles/{rol.pk}/?paso=2").content.decode()

        self.assertIn('name="leer_merma"', pagina)
        self.assertIn('name="escribir_merma"', pagina)

    def test_una_opción_apagada_se_va_del_asistente(self) -> None:
        Opcion.objects.create(clave="merma", nombre="Merma", grupo="Sistema", orden=99, activo=False)
        rol = Rol.objects.create(nombre="Ventas")

        pagina = self.client.get(f"/seguridad/roles/{rol.pk}/?paso=2").content.decode()

        self.assertNotIn("leer_merma", pagina)

    def test_una_opción_se_apaga_y_se_elimina(self) -> None:
        opcion = Opcion.objects.create(clave="merma", nombre="Merma", grupo="Sistema")

        self.client.post(f"/seguridad/opciones/{opcion.pk}/desactivar/")
        opcion.refresh_from_db()
        self.assertFalse(opcion.activo)

        self.client.post(f"/seguridad/opciones/{opcion.pk}/activar/")
        opcion.refresh_from_db()
        self.assertTrue(opcion.activo)

        self.client.post(f"/seguridad/opciones/{opcion.pk}/eliminar/")
        self.assertFalse(Opcion.objects.filter(clave="merma").exists())

    def test_al_eliminarla_se_van_sus_permisos(self) -> None:
        rol = _rol_con("Ventas", self.jefe, clientes=Nivel.LECTURA.value)
        opcion = de("clientes")

        self.client.post(f"/seguridad/opciones/{opcion.pk}/eliminar/")

        self.assertEqual(rol.opciones, {})

    def test_lo_que_no_es_una_acción_de_la_opción_da_404(self) -> None:
        opcion = Opcion.objects.create(clave="merma", nombre="Merma", grupo="Sistema")

        self.assertEqual(
            self.client.post(f"/seguridad/opciones/{opcion.pk}/bailar/").status_code, 404
        )


class PruebasDelAltaDeUsuarios(TestCase):
    """Crear personas desde la aplicación, sin pasar por el admin."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("quien-manda-usuarios", "jefe@ejemplo.ec", "clave-de-pruebas")
        self.client.force_login(self.jefe)
        self.rol = Rol.objects.create(nombre="Ventas")
        Permiso.objects.create(rol=self.rol, opcion="clientes", nivel=Nivel.LECTURA.value)

    def test_la_pantalla_de_alta_se_abre(self) -> None:
        pagina = self.client.get("/seguridad/usuarios/nuevo/").content.decode()

        self.assertIn("Nuevo usuario", pagina)
        self.assertIn('name="clave"', pagina)
        self.assertIn("Ventas", pagina)

    def test_se_crea_el_usuario_con_su_clave_y_su_rol(self) -> None:
        respuesta = self.client.post(
            "/seguridad/usuarios/nuevo/",
            {
                "username": "vendedor-nuevo",
                "first_name": "Ana",
                "last_name": "Pérez",
                "email": "ana@ejemplo.ec",
                "is_active": "on",
                "clave": "una-clave-larga-2026",
                "clave2": "una-clave-larga-2026",
                "roles": [self.rol.pk],
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        persona = User.objects.get(username="vendedor-nuevo")
        self.assertTrue(persona.check_password("una-clave-larga-2026"))
        self.assertTrue(persona.is_active)
        self.assertEqual(list(persona.roles.values_list("nombre", flat=True)), ["Ventas"])

    def test_el_usuario_creado_puede_entrar(self) -> None:
        self.client.post(
            "/seguridad/usuarios/nuevo/",
            {
                "username": "vendedor-entra",
                "clave": "otra-clave-larga-2026",
                "clave2": "otra-clave-larga-2026",
            },
        )
        otro = Client(SERVER_NAME="localhost")
        self.assertTrue(otro.login(username="vendedor-entra", password="otra-clave-larga-2026"))

    def test_no_se_repite_el_nombre_de_usuario(self) -> None:
        respuesta = self.client.post(
            "/seguridad/usuarios/nuevo/",
            {
                "username": "quien-manda-usuarios",
                "clave": "una-clave-larga-2026",
                "clave2": "una-clave-larga-2026",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Ya hay una cuenta con ese nombre", respuesta.content.decode())

    def test_las_dos_claves_tienen_que_coincidir(self) -> None:
        respuesta = self.client.post(
            "/seguridad/usuarios/nuevo/",
            {
                "username": "claves-distintas",
                "clave": "una-clave-larga-2026",
                "clave2": "otra-clave-larga-2026",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Las dos claves no son iguales", respuesta.content.decode())

    def test_una_clave_comun_no_se_acepta(self) -> None:
        respuesta = self.client.post(
            "/seguridad/usuarios/nuevo/",
            {
                "username": "clave-comun",
                "clave": "12345678",
                "clave2": "12345678",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(User.objects.filter(username="clave-comun").exists())

    def test_se_cambian_los_datos_y_la_clave(self) -> None:
        persona = User.objects.create_user("cambia-clave", password="clave-vieja-2026")

        respuesta = self.client.post(
            f"/seguridad/usuarios/{persona.pk}/datos/",
            {
                "username": "cambia-clave",
                "first_name": "Luis",
                "email": "luis@ejemplo.ec",
                "is_active": "on",
                "clave": "clave-nueva-2026",
                "clave2": "clave-nueva-2026",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        persona.refresh_from_db()
        self.assertEqual(persona.first_name, "Luis")
        self.assertTrue(persona.check_password("clave-nueva-2026"))

    def test_sin_la_clave_al_corregir_se_queda_la_que_tenia(self) -> None:
        persona = User.objects.create_user("sin-cambiar-clave", password="la-de-siempre-2026")

        self.client.post(
            f"/seguridad/usuarios/{persona.pk}/datos/",
            {"username": "sin-cambiar-clave", "first_name": "Marta", "is_active": "on"},
        )

        persona.refresh_from_db()
        self.assertEqual(persona.first_name, "Marta")
        self.assertTrue(persona.check_password("la-de-siempre-2026"))

    def test_se_puede_dar_de_baja_sin_borrar(self) -> None:
        persona = User.objects.create_user("se-va", password="clave-larga-2026")

        self.client.post(
            f"/seguridad/usuarios/{persona.pk}/datos/",
            {"username": "se-va", "clave": "", "clave2": ""},
        )

        persona.refresh_from_db()
        self.assertFalse(persona.is_active)
        self.assertTrue(User.objects.filter(username="se-va").exists())


class PruebasDeLasCategorias(TestCase):
    """Las opciones se agrupan por categoría en el asistente del rol."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("quien-categoriza", "jefe@ejemplo.ec", "clave-de-pruebas")
        self.client.force_login(self.jefe)

    def test_la_siembra_dejo_categorias(self) -> None:
        from personalize_options.models import Categoria, Opcion

        self.assertTrue(Categoria.objects.exists())
        self.assertEqual(Opcion.objects.filter(categoria__isnull=True).count(), 0)

    def test_el_asistente_del_rol_agrupa_por_categoria(self) -> None:
        from personalize_options.models import Categoria

        categoria = Categoria.objects.filter(nombre="Catálogo").first()
        rol = Rol.objects.create(nombre="Bodega")

        pagina = self.client.get(f"/seguridad/roles/{rol.pk}/?paso=2").content.decode()

        self.assertIn(categoria.nombre, pagina)
        self.assertIn("leer_clientes", pagina)

    def test_una_opcion_nueva_copia_el_apartado_de_su_categoria(self) -> None:
        from personalize_options.models import Categoria, Opcion

        categoria = Categoria.objects.get(nombre="Reportes")
        opcion = Opcion.objects.create(
            clave="reporte_de_prueba",
            nombre="Reporte de prueba",
            categoria=categoria,
        )

        opcion.refresh_from_db()
        self.assertEqual(opcion.grupo, "Reportes")
        self.assertEqual(opcion.categoria_nombre, "Reportes")


class PruebasDeLosAjustes(TestCase):
    """La configuración de la aplicación, sin pasar por el admin.

    Es lo que antes iba en `settings.py`: se ve en una pantalla, agrupada, y se
    cambia con el permiso de escritura. Quien sólo puede leer, lee.
    """

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser(
            "jefe-ajustes", "jefe@ejemplo.ec", "clave-larga-123"
        )

    def _entrar(self, usuario: User) -> None:
        self.client.force_login(usuario)
        self.client.get("/")  # la sesión necesita una vuelta

    def test_la_pantalla_enseña_los_ajustes_de_la_base(self) -> None:
        from personalize_options.models import Ajuste

        self._entrar(self.jefe)
        pagina = self.client.get("/seguridad/ajustes/")

        self.assertEqual(pagina.status_code, 200)
        texto = _texto(pagina.content.decode())
        for ajuste in Ajuste.objects.filter(editable=True)[:6]:
            self.assertIn(ajuste.clave, texto)

    def test_cada_bloque_dice_que_paquete_declara_sus_ajustes(self) -> None:
        self._entrar(self.jefe)
        texto = _texto(self.client.get("/seguridad/ajustes/").content.decode())

        # Los del paquete de permisos, los del SRI y los de cada aplicación.
        for origen in ("personalize_options", "factec", "inventario", "seguridad"):
            self.assertIn(origen, texto, origen)

    def test_la_clave_no_es_un_campo_que_se_escriba(self) -> None:
        # El nombre del ajuste es el que lee el código: aquí sólo se escribe el
        # valor.
        self._entrar(self.jefe)
        texto = self.client.get("/seguridad/ajustes/").content.decode()

        self.assertNotIn('name="clave" value="bloqueo_inactividad_minutos" type="text"', texto)
        self.assertIn('name="valor-bloqueo_inactividad_minutos"', texto)

    def test_guardar_cambia_el_ajuste_y_lo_deja_en_la_base(self) -> None:
        from personalize_options import ajustes as registro
        from personalize_options.models import Ajuste

        self._entrar(self.jefe)
        antes = Ajuste.objects.get(clave="bloqueo_inactividad_minutos").valor
        respuesta = self.client.post(
            "/seguridad/ajustes/",
            {"clave": ["bloqueo_inactividad_minutos"], "valor-bloqueo_inactividad_minutos": "45"},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            Ajuste.objects.get(clave="bloqueo_inactividad_minutos").valor, "45"
        )
        self.assertNotEqual(antes, "45")
        registro._leidos_de_la_base.cache_clear()

    def test_un_booleano_se_guarda_como_si_o_no(self) -> None:
        from personalize_options.models import Ajuste

        self._entrar(self.jefe)
        self.client.post(
            "/seguridad/ajustes/",
            {"clave": ["inventario_descontar_al_facturar"]},
            follow=True,
        )

        self.assertEqual(
            Ajuste.objects.get(clave="inventario_descontar_al_facturar").valor, "no"
        )

    def test_los_ajustes_del_sri_no_salen_aqui(self) -> None:
        # El SRI es otro paquete y tiene su tabla y su pantalla en el admin: en
        # esta no se mezclan.
        self._entrar(self.jefe)
        texto = self.client.get("/seguridad/ajustes/").content.decode()

        self.assertNotIn("sri_ambiente", texto)
        self.assertNotIn("sri_clave_cifrado", texto)

    def test_un_ajuste_de_solo_lectura_no_se_toca(self) -> None:
        from personalize_options.models import Ajuste

        objeto = Ajuste.objects.get(clave="modo")
        Ajuste.objects.filter(pk=objeto.pk).update(editable=False)

        self._entrar(self.jefe)
        self.client.post(
            "/seguridad/ajustes/",
            {"clave": ["modo"], "valor-modo": "inventado"},
            follow=True,
        )

        self.assertEqual(Ajuste.objects.get(clave="modo").valor, objeto.valor)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_quien_solo_lee_no_guarda(self) -> None:
        from personalize_options.models import Ajuste

        mirón = User.objects.create_user("mirón", password="clave-larga-123")
        _rol_con("sólo mira", mirón, ajustes=Nivel.LECTURA)
        self._entrar(mirón)

        self.assertEqual(self.client.get("/seguridad/ajustes/").status_code, 200)
        self.client.post(
            "/seguridad/ajustes/",
            {"clave": ["bloqueo_inactividad_minutos"], "valor-bloqueo_inactividad_minutos": "99"},
        )
        self.assertNotEqual(
            Ajuste.objects.get(clave="bloqueo_inactividad_minutos").valor, "99"
        )

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_sin_el_permiso_no_se_entra(self) -> None:
        nadie = User.objects.create_user("nadie", password="clave-larga-123")
        _rol_con("otros temas", nadie, clientes=Nivel.LECTURA)
        self._entrar(nadie)

        self.assertEqual(self.client.get("/seguridad/ajustes/").status_code, 403)


class PruebasDeMoverLasOpciones(TestCase):
    """Subir y bajar una opción de puesto, con las flechas."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser(
            "jefe-orden", "jefe@ejemplo.ec", "clave-larga-123"
        )
        self.client.force_login(self.jefe)
        self.client.get("/")

    def _orden(self, grupo: str = "Sistema") -> list:
        return list(
            Opcion.objects.filter(grupo=grupo).order_by("orden", "nombre").values_list("clave", flat=True)
        )

    def test_bajar_una_opcion_la_cambia_con_la_de_al_lado(self) -> None:
        antes = self._orden("Sistema")
        self.assertTrue(len(antes) >= 2, antes)

        primera = Opcion.objects.get(clave=antes[0])
        respuesta = self.client.post(f"/seguridad/opciones/{primera.pk}/mover/abajo/")

        self.assertEqual(respuesta.status_code, 302)
        despues = self._orden("Sistema")
        self.assertEqual(despues[0], antes[1])
        self.assertEqual(despues[1], antes[0])

    def test_subir_una_opcion_la_cambia_con_la_de_al_lado(self) -> None:
        antes = self._orden("Sistema")
        segunda = Opcion.objects.get(clave=antes[1])

        self.client.post(f"/seguridad/opciones/{segunda.pk}/mover/arriba/")

        despues = self._orden("Sistema")
        self.assertEqual(despues[0], antes[1])
        self.assertEqual(despues[1], antes[0])

    def test_en_el_extremo_no_pasa_nada(self) -> None:
        antes = self._orden("Sistema")
        primera = Opcion.objects.get(clave=antes[0])

        self.client.post(f"/seguridad/opciones/{primera.pk}/mover/arriba/")

        self.assertEqual(self._orden("Sistema"), antes)

    def test_el_orden_queda_numerado_sin_huecos(self) -> None:
        opcion = Opcion.objects.filter(grupo="Sistema").order_by("orden").first()
        self.client.post(f"/seguridad/opciones/{opcion.pk}/mover/abajo/")

        numeros = list(
            Opcion.objects.filter(grupo="Sistema").order_by("orden").values_list("orden", flat=True)
        )
        self.assertEqual(numeros, list(range(1, len(numeros) + 1)))

    def test_la_pantalla_enseña_las_flechas(self) -> None:
        pagina = self.client.get("/seguridad/opciones/ordenar/")
        texto = pagina.content.decode()

        self.assertEqual(pagina.status_code, 200)
        self.assertIn("mover/arriba", texto)
        self.assertIn("mover/abajo", texto)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_quien_solo_lee_no_mueve_nada(self) -> None:
        mirón = User.objects.create_user("mirón-orden", password="clave-larga-123")
        _rol_con("sólo mira el menú", mirón, opciones=Nivel.LECTURA)
        self.client.force_login(mirón)
        self.client.get("/")

        antes = self._orden("Sistema")
        primera = Opcion.objects.get(clave=antes[0])
        respuesta = self.client.post(f"/seguridad/opciones/{primera.pk}/mover/abajo/")

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self._orden("Sistema"), antes)

    def test_la_lista_principal_tambien_trae_las_flechas(self) -> None:
        pagina = self.client.get("/seguridad/opciones/")
        texto = pagina.content.decode()

        self.assertEqual(pagina.status_code, 200)
        self.assertIn("mover/arriba", texto)
        self.assertIn("mover/abajo", texto)

    def test_despues_de_mover_vuelve_a_donde_estaba(self) -> None:
        primera = Opcion.objects.filter(grupo="Sistema").order_by("orden").first()

        respuesta = self.client.post(
            f"/seguridad/opciones/{primera.pk}/mover/abajo/",
            {"volver": "/seguridad/opciones/?q=usuarios"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], "/seguridad/opciones/?q=usuarios")

    def test_no_vuelve_a_otro_sitio(self) -> None:
        # La dirección de vuelta se comprueba: no vale cualquier cosa.
        primera = Opcion.objects.filter(grupo="Sistema").order_by("orden").first()

        respuesta = self.client.post(
            f"/seguridad/opciones/{primera.pk}/mover/abajo/",
            {"volver": "https://ejemplo-fuera.ec/robo"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], "/seguridad/opciones/ordenar/")
