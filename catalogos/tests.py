"""Pruebas del catálogo: productos, servicios y clientes.

Las listas cuentan lo que se ha facturado de cada uno. Es una cuenta que se hace
con las líneas de las facturas, porque el paquete no deja la relación inversa
desde el producto: si se cambia, aquí se ve.
"""

from __future__ import annotations

import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from factec.django.documentos import (
    Cliente,
    Conductor,
    Factura,
    FacturaDetalle,
    GuiaRemision,
    Producto,
    Vehiculo,
)

from inventario.models import Existencia
from tienda.models import ProductoTienda

__all__ = [
    "PruebasDelCatalogo",
    "PruebasDelTransporte",
    "PruebasDeLaTiendaEnElCatalogo",
]


class PruebasDelCatalogo(TestCase):
    """Altas y listas."""

    def setUp(self) -> None:
        User.objects.create_user("quien-lleva-el-catalogo", password="x")
        self.client.force_login(User.objects.get(username="quien-lleva-el-catalogo"))

    def test_el_formulario_acepta_la_coma_y_deja_la_existencia_inicial(self) -> None:
        respuesta = self.client.post(
            "/wadmin/catalogos/productos/nuevo/",
            {
                "tipo": "producto",
                "codigo_principal": "CAJA-12",
                "descripcion": "CAJA DE DOCE",
                "unidad_medida": "CAJA",
                "precio_unitario": "10,50",
                "codigo_porcentaje_iva": "4",
                "activo": "on",
                "stock_inicial": "12",
                "minimo": "5",
                "ubicacion": "bodega",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        producto = Producto.objects.get()
        self.assertEqual(producto.precio_unitario, Decimal("10.5"))
        existencia = Existencia.objects.get(producto=producto)
        self.assertEqual(existencia.cantidad, Decimal("12"))
        self.assertEqual(existencia.ubicacion, "bodega")

    def test_la_lista_dice_cuantas_veces_se_ha_facturado_cada_producto(self) -> None:
        producto = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario="10.50", codigo_porcentaje_iva="4",
        )
        receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA", identificacion="1790012345001",
            tipo_identificacion="04",
        )
        factura = Factura.objects.create(receptor=receptor, fecha_emision="2026-01-15")
        FacturaDetalle.objects.create(
            factura=factura, producto=producto, descripcion="CAJA DE DOCE",
            cantidad=Decimal("2"), precio_unitario=Decimal("10.50"),
        )

        respuesta = self.client.get("/wadmin/catalogos/productos/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("1 vez facturado", respuesta.content.decode())

    def test_la_lista_de_clientes_dice_cuantas_facturas_tiene_cada_uno(self) -> None:
        receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA", identificacion="1790012345001",
            tipo_identificacion="04",
        )
        Factura.objects.create(receptor=receptor, fecha_emision="2026-01-15")

        respuesta = self.client.get("/wadmin/catalogos/clientes/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("CLIENTE DE PRUEBA", respuesta.content.decode())

    def test_los_avisos_del_servidor_salen_marcados_para_el_aviso_flotante(self) -> None:
        """El aviso se marca con su tipo: interfaz.js lo levanta como aviso de Metro."""
        respuesta = self.client.post(
            "/wadmin/catalogos/productos/nuevo/",
            {
                "tipo": "servicio",
                "codigo_principal": "HORA",
                "descripcion": "HORA DE CONSULTORIA",
                "unidad_medida": "HORA",
                "precio_unitario": "25",
                "codigo_porcentaje_iva": "4",
                "activo": "on",
            },
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('data-aviso="success"', respuesta.content.decode())

    def test_la_lista_de_productos_es_un_listado(self) -> None:
        """La lista la monta Metro, que es la que trae buscador y paginación, y se
        lee como un listado: cada fila con su marca, sin cabecera de columnas."""
        Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario="10.50", codigo_porcentaje_iva="4",
        )

        pagina = self.client.get("/wadmin/catalogos/productos/").content.decode()

        self.assertIn('id="tabla-productos"', pagina)
        self.assertIn("data-tabla", pagina)
        self.assertIn("listado", pagina)
        self.assertIn('class="col-marca"', pagina)
        self.assertIn('class="col-principal"', pagina)

    def test_el_listado_muestra_el_precio_con_iva(self) -> None:
        """El precio guardado es sin IVA: la lista enseña lo que paga el cliente y
        el desglose al lado, para que nadie tenga que hacer la cuenta."""
        Producto.objects.create(
            tipo="servicio", codigo_principal="HORA", descripcion="HORA DE CONSULTORIA",
            precio_unitario="10.50", codigo_porcentaje_iva="4",
        )

        pagina = self.client.get("/wadmin/catalogos/productos/").content.decode()

        self.assertIn("12,08", pagina)  # 10,50 más el 15 %
        self.assertIn("10,50 + IVA 15%", pagina)

    def test_un_precio_sin_iva_no_suma_nada(self) -> None:
        """Exento de IVA: el precio de la lista es el mismo de la ficha."""
        Producto.objects.create(
            tipo="servicio", codigo_principal="HORA", descripcion="HORA DE CONSULTORIA",
            precio_unitario="10.00", codigo_porcentaje_iva="7",
        )

        pagina = self.client.get("/wadmin/catalogos/productos/").content.decode()

        self.assertIn("10,00 + Exento de IVA", pagina)


class PruebasDelTransporte(TestCase):
    """Los conductores y los vehículos de la guía de remisión: altas y listas."""

    def setUp(self) -> None:
        User.objects.create_user("quien-lleva-el-transporte", password="clave-de-pruebas")
        self.client.force_login(User.objects.get(username="quien-lleva-el-transporte"))

    def test_se_da_de_alta_un_conductor(self) -> None:
        respuesta = self.client.post(
            "/wadmin/catalogos/conductores/nuevo/",
            {
                "razon_social": "TRANSPORTES DEL NORTE CÍA. LTDA.",
                "tipo_identificacion": "04",
                "identificacion": "1790012345001",
                "telefono": "0999999999",
                "activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        conductor = Conductor.objects.get()
        self.assertEqual(conductor.identificacion, "1790012345001")
        self.assertTrue(conductor.activo)

    def test_se_da_de_alta_un_vehiculo(self) -> None:
        respuesta = self.client.post(
            "/wadmin/catalogos/vehiculos/nuevo/",
            {"placa": "PBX-1234", "descripcion": "Camión Hino", "activo": "on"},
        )

        self.assertEqual(respuesta.status_code, 302)
        vehiculo = Vehiculo.objects.get()
        self.assertEqual(vehiculo.placa, "PBX-1234")
        self.assertEqual(vehiculo.descripcion, "Camión Hino")

    def test_el_conductor_se_puede_corregir(self) -> None:
        conductor = Conductor.objects.create(
            razon_social="TRANSPORTES DEL NORTE", identificacion="1790012345001",
        )

        respuesta = self.client.post(
            f"/wadmin/catalogos/conductores/{conductor.pk}/",
            {
                "razon_social": "TRANSPORTES DEL SUR",
                "tipo_identificacion": "04",
                "identificacion": "1790012345001",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        conductor.refresh_from_db()
        self.assertEqual(conductor.razon_social, "TRANSPORTES DEL SUR")
        self.assertFalse(conductor.activo)  # la casilla sin marcar retira del catálogo

    def test_la_lista_de_conductores_cuenta_sus_guias(self) -> None:
        """La guía guarda el RUC del transportista, no una relación: así se cuenta."""
        conductor = Conductor.objects.create(
            razon_social="TRANSPORTES DEL NORTE", identificacion="1790012345001",
            tipo_identificacion="04",
        )
        GuiaRemision.objects.create(
            fecha_emision="2026-01-15", dir_partida="QUITO",
            razon_social_transportista=conductor.razon_social,
            ruc_transportista=conductor.identificacion, placa="PBX-1234",
            fecha_ini_transporte="2026-01-15", fecha_fin_transporte="2026-01-15",
        )

        respuesta = self.client.get("/wadmin/catalogos/conductores/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["conductores"][0].cuantas_guias, 1)

    def test_la_lista_de_vehiculos_cuenta_sus_guias(self) -> None:
        vehiculo = Vehiculo.objects.create(placa="PBX-1234", descripcion="Camión")
        GuiaRemision.objects.create(
            fecha_emision="2026-01-15", dir_partida="QUITO",
            razon_social_transportista="TRANSPORTES", ruc_transportista="1790012345001",
            placa=vehiculo.placa,
            fecha_ini_transporte="2026-01-15", fecha_fin_transporte="2026-01-15",
        )

        respuesta = self.client.get("/wadmin/catalogos/vehiculos/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["vehiculos"][0].cuantas_guias, 1)

    def test_las_listas_se_pueden_buscar(self) -> None:
        Conductor.objects.create(
            razon_social="TRANSPORTES DEL NORTE", identificacion="1790012345001",
        )
        Vehiculo.objects.create(placa="PBX-1234")

        conductores = self.client.get("/wadmin/catalogos/conductores/", {"q": "norte"})
        vehiculos = self.client.get("/wadmin/catalogos/vehiculos/", {"q": "no-existe"})

        self.assertEqual(conductores.context["cuantos"], 1)
        self.assertEqual(vehiculos.context["cuantos"], 0)


class PruebasDeLaTiendaEnElCatalogo(TestCase):
    """La tienda se gestiona en la misma pantalla del producto, no en otra alta."""

    @classmethod
    def setUpClass(cls):
        cls.carpeta = tempfile.mkdtemp()
        cls.override = override_settings(MEDIA_ROOT=cls.carpeta)
        cls.override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.override.disable()
        shutil.rmtree(cls.carpeta, ignore_errors=True)

    def setUp(self) -> None:
        User.objects.create_user("quien-lleva-el-catalogo", password="clave")
        self.client.force_login(User.objects.get(username="quien-lleva-el-catalogo"))

    def datos(self, **extra):
        """Lo que se envía en la pantalla del producto (la parte fiscal)."""
        datos = {
            "tipo": "producto",
            "codigo_principal": "CAJA-12",
            "descripcion": "CAJA DE DOCE",
            "unidad_medida": "CAJA",
            "precio_unitario": "10,50",
            "codigo_porcentaje_iva": "4",
            "activo": "on",
            "minimo": "0",
            "ubicacion": "",
        }
        datos.update(extra)
        return datos

    def datos_de_tienda(self, **extra):
        """Lo que se envía en la sección «En la tienda»."""
        datos = {
            "publicado": "on",
            "destacado": "",
            "categoria": "",
            "orden": "0",
            "titulo": "Caja de doce",
            "resumen": "Doce unidades",
            "descripcion_larga": "",
            "precio_web": "9,99",
            "precio_oferta": "",
            "oferta_desde": "",
            "oferta_hasta": "",
            "peso": "",
        }
        datos.update(extra)
        return datos

    def test_la_pantalla_del_producto_trae_la_tienda(self) -> None:
        producto = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario=Decimal("10.50"), unidad_medida="CAJA",
        )
        respuesta = self.client.get(f"/wadmin/catalogos/productos/{producto.pk}/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "En la tienda")

    def test_la_pantalla_lleva_a_ver_la_ficha_en_la_tienda(self) -> None:
        """Desde el producto se mira cómo queda en la web, sin buscar la dirección."""
        producto = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario=Decimal("10.50"), unidad_medida="CAJA",
        )
        tienda = ProductoTienda.extender(producto)
        tienda.publicado = True
        tienda.save()

        respuesta = self.client.get(f"/wadmin/catalogos/productos/{producto.pk}/")

        self.assertContains(respuesta, "verla en la tienda")
        self.assertContains(respuesta, f"/p/{tienda.slug}/")

    def test_lo_que_no_esta_publicado_no_ofrece_verlo_en_la_tienda(self) -> None:
        producto = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario=Decimal("10.50"), unidad_medida="CAJA",
        )
        tienda = ProductoTienda.extender(producto)
        tienda.publicado = False
        tienda.save()

        respuesta = self.client.get(f"/wadmin/catalogos/productos/{producto.pk}/")

        self.assertNotContains(respuesta, "verla en la tienda")

    def test_el_producto_se_publica_desde_su_pantalla(self) -> None:
        foto = SimpleUploadedFile("frente.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        datos = self.datos()
        datos.update(self.datos_de_tienda())
        datos.update({
            "imagenes-TOTAL_FORMS": "1",
            "imagenes-INITIAL_FORMS": "0",
            "imagenes-MIN_NUM_FORMS": "0",
            "imagenes-MAX_NUM_FORMS": "1000",
            "imagenes-0-imagen": foto,
            "imagenes-0-alt": "Caja de frente",
            "imagenes-0-orden": "0",
        })

        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Producto.objects.count(), 1)
        producto = Producto.objects.get()
        tienda = ProductoTienda.de(producto)
        self.assertIsNotNone(tienda)
        self.assertTrue(tienda.publicado)
        self.assertEqual(tienda.titulo, "Caja de doce")
        self.assertEqual(tienda.precio_web, Decimal("9.99"))
        self.assertEqual(tienda.slug, "caja-de-doce")
        self.assertEqual(tienda.imagenes.count(), 1)
        self.assertEqual(producto.descripcion, "CAJA DE DOCE")
        self.assertEqual(producto.precio_unitario, Decimal("10.50"))

    def test_sin_datos_de_tienda_el_producto_no_se_publica(self) -> None:
        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", self.datos())
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(ProductoTienda.objects.count(), 0)

    def test_se_puede_despublicar_desde_la_misma_pantalla(self) -> None:
        producto = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario=Decimal("10.50"), unidad_medida="CAJA",
        )
        tienda = ProductoTienda.extender(producto)
        tienda.publicado = True
        tienda.titulo = "Caja de doce"
        tienda.save()

        datos = self.datos()
        datos.update(self.datos_de_tienda(publicado="", titulo="", precio_web=""))
        respuesta = self.client.post(f"/wadmin/catalogos/productos/{producto.pk}/", datos)

        self.assertEqual(respuesta.status_code, 302)
        tienda = ProductoTienda.de(Producto.objects.get(pk=producto.pk))
        self.assertFalse(tienda.publicado)
        self.assertEqual(tienda.titulo, "")
        self.assertEqual(ProductoTienda.objects.count(), 1)

    def test_la_lista_marca_lo_que_esta_en_la_tienda(self) -> None:
        producto = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            precio_unitario=Decimal("10.50"), unidad_medida="CAJA",
        )
        tienda = ProductoTienda.extender(producto)
        tienda.publicado = True
        tienda.save()

        respuesta = self.client.get("/wadmin/catalogos/productos/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "en la tienda")

    def test_si_la_tienda_no_valida_el_producto_no_se_guarda(self) -> None:
        datos = self.datos()
        datos.update(self.datos_de_tienda(precio_web="10,00", precio_oferta="12,00"))

        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Producto.objects.count(), 0)
        self.assertEqual(ProductoTienda.objects.count(), 0)

    def test_una_fila_de_fotos_sin_archivo_no_estropa_el_guardado(self) -> None:
        """El navegador puede dejar puesto el alt de una foto que no se eligió."""
        datos = self.datos()
        datos.update(self.datos_de_tienda(publicado="", titulo="", precio_web=""))
        datos.update({
            "imagenes-TOTAL_FORMS": "1",
            "imagenes-INITIAL_FORMS": "0",
            "imagenes-MIN_NUM_FORMS": "0",
            "imagenes-MAX_NUM_FORMS": "1000",
            "imagenes-0-id": "",
            "imagenes-0-alt": "CAJA DE DOCE",
            "imagenes-0-orden": "0",
        })

        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", datos)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Producto.objects.count(), 1)

    def test_un_video_se_guarda_como_video_y_la_principal_sigue_siendo_la_foto(self) -> None:
        """En «Fotos y videos» caben los dos, y el video no le quita la portada a la foto."""
        from tienda.models import ImagenProducto

        foto = SimpleUploadedFile("frente.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        video = SimpleUploadedFile(
            "demo.mp4", b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4"
        )
        datos = self.datos()
        datos.update(self.datos_de_tienda(publicado="", titulo="", precio_web=""))
        datos.update({
            "imagenes-TOTAL_FORMS": "2",
            "imagenes-INITIAL_FORMS": "0",
            "imagenes-MIN_NUM_FORMS": "0",
            "imagenes-MAX_NUM_FORMS": "1000",
            "imagenes-0-id": "",
            "imagenes-0-imagen": foto,
            "imagenes-0-alt": "Caja de frente",
            "imagenes-0-orden": "0",
            "imagenes-1-id": "",
            "imagenes-1-imagen": video,
            "imagenes-1-alt": "Caja en movimiento",
            "imagenes-1-orden": "1",
        })

        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", datos)

        self.assertEqual(respuesta.status_code, 302)
        guardadas = list(ImagenProducto.objects.order_by("orden"))
        self.assertEqual(len(guardadas), 2)
        self.assertFalse(guardadas[0].es_video)
        self.assertTrue(guardadas[1].es_video)
        self.assertEqual(guardadas[1].extension, "mp4")

        tienda = ProductoTienda.de(Producto.objects.get())
        self.assertIsNotNone(tienda)
        self.assertEqual(tienda.imagen_principal, guardadas[0])

    def test_una_foto_mal_puesta_se_queda_en_la_pantalla(self) -> None:
        """Con un error de verdad se ve en la pantalla, no en un aviso que se va."""
        foto = SimpleUploadedFile("frente.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        datos = self.datos()
        datos.update(self.datos_de_tienda(publicado="", titulo="", precio_web=""))
        datos.update({
            "imagenes-TOTAL_FORMS": "1",
            "imagenes-INITIAL_FORMS": "0",
            "imagenes-MIN_NUM_FORMS": "0",
            "imagenes-MAX_NUM_FORMS": "1000",
            "imagenes-0-imagen": foto,
            "imagenes-0-alt": "Caja de frente",
            "imagenes-0-orden": "no es un número",
        })

        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "revise las fotos de la tienda")
        self.assertEqual(Producto.objects.count(), 1)

    def test_una_foto_sola_ya_guarda_la_parte_de_tienda(self) -> None:
        foto = SimpleUploadedFile("frente.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        datos = self.datos()
        datos.update(self.datos_de_tienda(publicado="", titulo="", precio_web=""))
        datos.update({
            "imagenes-TOTAL_FORMS": "1",
            "imagenes-INITIAL_FORMS": "0",
            "imagenes-MIN_NUM_FORMS": "0",
            "imagenes-MAX_NUM_FORMS": "1000",
            "imagenes-0-imagen": foto,
            "imagenes-0-alt": "Caja de frente",
            "imagenes-0-orden": "0",
        })

        respuesta = self.client.post("/wadmin/catalogos/productos/nuevo/", datos)

        self.assertEqual(respuesta.status_code, 302)
        tienda = ProductoTienda.de(Producto.objects.get())
        self.assertIsNotNone(tienda)
        self.assertFalse(tienda.publicado)
        self.assertEqual(tienda.imagenes.count(), 1)
