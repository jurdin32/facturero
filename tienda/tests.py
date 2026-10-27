"""Pruebas de la tienda.

Lo que se prueba es la costura con el catálogo fiscal: que extender un producto no
lo duplique ni le cambie nada, que el precio se muestre con IVA y con la oferta
solo cuando toca, y que lo no publicado no salga en las consultas del catálogo.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from factec.django.documentos import Cliente, Factura, Producto

from inventario.models import Existencia

from .carrito import Carrito
from .models import (
    Categoria,
    ImagenProducto,
    LineaPedido,
    Pedido,
    Pregunta,
    ProductoTienda,
    Resena,
)

__all__ = [
    "PruebasDeLaCategoria",
    "PruebasDelCatalogo",
    "PruebasDelPrecio",
    "PruebasDelStock",
    "PruebasDeLaExtension",
    "PruebasDeLasImagenes",
    "PruebasDelAdmin",
    "PruebasDelCarrito",
    "PruebasDeLaTiendaPublica",
    "PruebasDeLosPedidos",
    "PruebasDeLasCategorias",
    "PruebasDelListado",
    "PruebasDelTextoEnriquecido",
    "PruebasDeLasPreguntas",
    "PruebasDeLasResenas",
    "PruebasDelSeguimientoDelPedido",
    "PruebasDelEditorDeLaDescripcion",
    "PruebasDeLoQueSeMiro",
]


def crear_producto(codigo: str = "P-001", descripcion: str = "Camiseta azul", **extra) -> Producto:
    """Un producto del catálogo fiscal, que es el que se extiende."""
    extra.setdefault("precio_unitario", Decimal("10.00"))
    return Producto.objects.create(
        codigo_principal=codigo, descripcion=descripcion, **extra
    )


def crear_en_tienda(codigo: str = "P-001", **extra) -> ProductoTienda:
    """Un producto del catálogo, ya extendido para la tienda."""
    extra.setdefault("descripcion", "Camiseta azul")
    extra.setdefault("precio_unitario", Decimal("10.00"))
    return ProductoTienda.objects.create(codigo_principal=codigo, **extra)


class PruebasDeLaCategoria(TestCase):
    """El árbol del catálogo: direcciones, rutas y ramas que no se muerden."""

    def test_el_slug_sale_del_nombre(self):
        categoria = Categoria.objects.create(nombre="Ropa de niño")
        self.assertEqual(categoria.slug, "ropa-de-nino")

    def test_el_slug_repetido_se_numera(self):
        Categoria.objects.create(nombre="Ropa")
        segunda = Categoria.objects.create(nombre="Ropa")
        self.assertEqual(segunda.slug, "ropa-2")

    def test_el_slug_escrito_a_mano_se_respeta(self):
        categoria = Categoria.objects.create(nombre="Ropa", slug="moda")
        self.assertEqual(categoria.slug, "moda")

    def test_la_ruta_sube_por_las_categorias(self):
        ropa = Categoria.objects.create(nombre="Ropa")
        camisetas = Categoria.objects.create(nombre="Camisetas", padre=ropa)
        manga = Categoria.objects.create(nombre="Manga corta", padre=camisetas)
        self.assertEqual(manga.ruta, "Ropa › Camisetas › Manga corta")

    def test_una_categoria_no_cuelga_de_si_misma(self):
        ropa = Categoria.objects.create(nombre="Ropa")
        ropa.padre = ropa
        with self.assertRaises(ValidationError):
            ropa.full_clean()

    def test_una_categoria_no_cuelga_de_su_hija(self):
        ropa = Categoria.objects.create(nombre="Ropa")
        camisetas = Categoria.objects.create(nombre="Camisetas", padre=ropa)
        ropa.padre = camisetas
        with self.assertRaises(ValidationError):
            ropa.full_clean()

    def test_la_rama_trae_a_las_hijas(self):
        ropa = Categoria.objects.create(nombre="Ropa")
        camisetas = Categoria.objects.create(nombre="Camisetas", padre=ropa)
        zapatos = Categoria.objects.create(nombre="Zapatos")
        self.assertCountEqual(ropa.con_descendientes(), [ropa.pk, camisetas.pk])
        self.assertNotIn(zapatos.pk, ropa.con_descendientes())


class PruebasDeLaExtension(TestCase):
    """Extender un producto es sumarle columnas, no crear otro producto."""

    def test_el_producto_extendido_es_el_mismo_producto(self):
        producto = crear_producto()
        extendido = ProductoTienda.extender(producto)
        self.assertEqual(extendido.pk, producto.pk)
        self.assertIsInstance(extendido, Producto)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertEqual(ProductoTienda.objects.count(), 1)

    def test_extender_no_le_cambia_nada_al_producto(self):
        producto = crear_producto(descripcion="Camiseta azul", precio_unitario=Decimal("12.34"))
        ProductoTienda.extender(producto)
        padre = Producto.objects.get(pk=producto.pk)
        self.assertEqual(padre.descripcion, "Camiseta azul")
        self.assertEqual(padre.precio_unitario, Decimal("12.34"))
        self.assertTrue(padre.activo)

    def test_extender_dos_veces_no_duplica(self):
        producto = crear_producto()
        primera = ProductoTienda.extender(producto)
        segunda = ProductoTienda.extender(Producto.objects.get(pk=producto.pk))
        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(ProductoTienda.objects.count(), 1)

    def test_la_extension_se_encuentra_desde_el_producto(self):
        producto = crear_producto()
        self.assertIsNone(ProductoTienda.de(producto))
        extendido = ProductoTienda.extender(producto)
        self.assertEqual(ProductoTienda.de(producto), extendido)
        self.assertIsNone(ProductoTienda.de(None))

    def test_lo_no_extendido_no_esta_en_la_tienda(self):
        producto = crear_producto()
        self.assertEqual(ProductoTienda.objects.publicadas().count(), 0)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertTrue(producto.activo)


class PruebasDelPrecio(TestCase):
    """El precio se guarda sin impuestos y se muestra con IVA, como en la tienda."""

    def test_sin_precio_de_web_se_usa_el_del_producto(self):
        producto = crear_en_tienda()
        self.assertEqual(producto.precio_sin_iva, Decimal("10.00"))
        self.assertEqual(producto.precio, Decimal("11.50"))     # 15 % de IVA
        self.assertIsNone(producto.precio_anterior)
        self.assertEqual(producto.descuento, 0)

    def test_el_precio_de_la_web_manda(self):
        producto = crear_en_tienda(precio_web=Decimal("20.00"))
        self.assertEqual(producto.precio, Decimal("23.00"))

    def test_la_oferta_vigente_manda_y_deja_el_precio_anterior(self):
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"), precio_oferta=Decimal("15.00")
        )
        self.assertTrue(producto.oferta_vigente)
        self.assertEqual(producto.precio_sin_iva, Decimal("15.00"))
        self.assertEqual(producto.precio, Decimal("17.25"))
        self.assertEqual(producto.precio_anterior, Decimal("23.00"))
        self.assertEqual(producto.descuento, 25)

    def test_una_oferta_vencida_no_se_aplica(self):
        ayer = timezone.localdate() - timedelta(days=1)
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
            oferta_hasta=ayer,
        )
        self.assertFalse(producto.oferta_vigente)
        self.assertEqual(producto.precio, Decimal("23.00"))
        self.assertIsNone(producto.precio_anterior)

    def test_una_oferta_que_empieza_manana_todavia_no_se_aplica(self):
        manana = timezone.localdate() + timedelta(days=1)
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
            oferta_desde=manana,
        )
        self.assertFalse(producto.oferta_vigente)
        self.assertEqual(producto.precio, Decimal("23.00"))

    def test_la_oferta_del_dia_limite_si_cuenta(self):
        hoy = timezone.localdate()
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
            oferta_desde=hoy,
            oferta_hasta=hoy,
        )
        self.assertTrue(producto.oferta_vigente)

    def test_una_oferta_que_no_descuenta_no_vale(self):
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"), precio_oferta=Decimal("20.00")
        )
        self.assertFalse(producto.oferta_vigente)

    def test_el_iva_del_producto_es_el_que_se_suma(self):
        producto = crear_en_tienda(codigo_porcentaje_iva="0", precio_web=Decimal("10.00"))
        self.assertEqual(producto.precio, Decimal("10.00"))

    def test_la_oferta_tiene_que_ser_menor(self):
        producto = ProductoTienda(
            codigo_principal="P-001",
            descripcion="Camiseta",
            precio_unitario=Decimal("10.00"),
            precio_web=Decimal("10.00"),
            precio_oferta=Decimal("12.00"),
        )
        with self.assertRaises(ValidationError):
            producto.full_clean()

    def test_la_oferta_no_puede_terminar_antes_de_empezar(self):
        hoy = timezone.localdate()
        producto = ProductoTienda(
            codigo_principal="P-001",
            descripcion="Camiseta",
            precio_unitario=Decimal("10.00"),
            precio_oferta=Decimal("5.00"),
            oferta_desde=hoy,
            oferta_hasta=hoy - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            producto.full_clean()

    def test_una_oferta_que_empieza_mas_adelante_se_anuncia(self):
        manana = timezone.localdate() + timedelta(days=1)
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
            oferta_desde=manana,
        )
        self.assertFalse(producto.oferta_vigente)
        self.assertTrue(producto.oferta_programada)

    def test_una_oferta_vencida_no_se_anuncia(self):
        ayer = timezone.localdate() - timedelta(days=1)
        producto = crear_en_tienda(
            precio_web=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
            oferta_hasta=ayer,
        )
        self.assertFalse(producto.oferta_programada)


class PruebasDelCatalogo(TestCase):
    """Lo que las consultas de la tienda dejan ver."""

    def test_solo_salen_las_publicadas_de_productos_activos(self):
        publicada = crear_en_tienda(publicado=True)
        crear_en_tienda(codigo="P-002", publicado=False)
        crear_en_tienda(codigo="P-003", publicado=True, activo=False)
        self.assertCountEqual(
            ProductoTienda.objects.publicadas(), [publicada]
        )

    def test_las_destacadas_son_las_publicadas_y_marcadas(self):
        destacada = crear_en_tienda(publicado=True, destacado=True)
        crear_en_tienda(codigo="P-002", publicado=True)
        crear_en_tienda(codigo="P-003", publicado=False, destacado=True)
        self.assertCountEqual(
            ProductoTienda.objects.destacadas(), [destacada]
        )

    def test_una_categoria_trae_lo_de_sus_subcategorias(self):
        ropa = Categoria.objects.create(nombre="Ropa")
        camisetas = Categoria.objects.create(nombre="Camisetas", padre=ropa)
        en_ropa = crear_en_tienda(publicado=True, categoria=ropa)
        en_camisetas = crear_en_tienda(codigo="P-002", publicado=True, categoria=camisetas)
        crear_en_tienda(
            codigo="P-003", publicado=True,
            categoria=Categoria.objects.create(nombre="Zapatos"),
        )
        self.assertCountEqual(
            ProductoTienda.objects.en_categoria(ropa), [en_ropa, en_camisetas]
        )

    def test_una_categoria_sin_rama_no_trae_nada(self):
        crear_en_tienda(publicado=True)
        self.assertFalse(ProductoTienda.objects.en_categoria(None).exists())

    def test_publicado_en_la_web_mira_tambien_el_producto(self):
        producto = crear_en_tienda(publicado=True)
        self.assertTrue(producto.publicado_en_la_web)
        producto.activo = False
        self.assertFalse(producto.publicado_en_la_web)

    def test_el_nombre_de_la_web_manda_sobre_la_descripcion(self):
        producto = crear_en_tienda(titulo="Camiseta de algodón")
        self.assertEqual(producto.nombre, "Camiseta de algodón")
        producto.titulo = ""
        self.assertEqual(producto.nombre, "Camiseta azul")


class PruebasDelStock(TestCase):
    """Un servicio no se agota y un bien sin inventario no se marca agotado."""

    def test_el_servicio_siempre_esta_disponible(self):
        producto = crear_en_tienda(tipo="servicio")
        self.assertTrue(producto.con_stock)

    def test_un_bien_con_existencia_se_mira_en_el_inventario(self):
        producto = crear_en_tienda()
        existencia = Existencia.objects.create(producto=producto, cantidad=Decimal("2"))
        self.assertTrue(producto.con_stock)
        existencia.cantidad = Decimal("0")
        existencia.save()
        self.assertFalse(producto.con_stock)

    def test_un_bien_sin_fila_de_existencia_se_da_por_disponible(self):
        producto = crear_en_tienda()
        self.assertTrue(producto.con_stock)


class PruebasDeLasImagenes(TestCase):
    """Las fotos, en orden: la primera es la que sale en el listado."""

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

    def setUp(self):
        self.producto = crear_en_tienda()

    def _imagen(self, nombre: str, orden: int) -> ImagenProducto:
        archivo = SimpleUploadedFile(nombre, b"\x89PNG\r\n\x1a\n", content_type="image/png")
        return ImagenProducto.objects.create(
            producto=self.producto, imagen=archivo, alt=nombre, orden=orden
        )

    def test_la_primera_por_orden_es_la_principal(self):
        segunda = self._imagen("atras.png", 2)
        primera = self._imagen("frente.png", 0)
        self.assertEqual(self.producto.imagen_principal, primera)
        self.assertNotEqual(self.producto.imagen_principal, segunda)

    def test_una_extension_que_no_es_foto_se_rechaza(self):
        archivo = SimpleUploadedFile("ficha.pdf", b"%PDF-1.4", content_type="application/pdf")
        imagen = ImagenProducto(producto=self.producto, imagen=archivo)
        with self.assertRaises(ValidationError):
            imagen.full_clean()


class PruebasDelAdmin(TestCase):
    """Las pantallas del admin cargan y el inline publica el producto existente."""

    def setUp(self):
        self.usuario = User.objects.create_superuser("admin", "admin@example.com", "clave")
        self.client.force_login(self.usuario)

    def test_las_pantallas_de_la_tienda_cargan(self):
        producto = crear_en_tienda(publicado=True)
        for url in (
            reverse("admin:tienda_productotienda_changelist"),
            reverse("admin:tienda_productotienda_change", args=[producto.pk]),
            reverse("admin:tienda_categoria_changelist"),
            reverse("admin:tienda_imagenproducto_changelist"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_el_producto_se_edita_con_su_parte_de_tienda_al_lado(self):
        producto = crear_producto()
        respuesta = self.client.get(
            reverse("admin:sri_fe_producto_change", args=[producto.pk])
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "En la tienda")

    def test_desde_el_producto_se_crea_la_extension(self):
        producto = crear_producto()
        datos = {
            "tipo": "producto",
            "codigo_principal": producto.codigo_principal,
            "codigo_auxiliar": "",
            "descripcion": producto.descripcion,
            "unidad_medida": producto.unidad_medida,
            "precio_unitario": "10.00",
            "codigo_porcentaje_iva": "4",
            "datos_adicionales": "",
            "activo": "on",
            "productotienda-TOTAL_FORMS": "1",
            "productotienda-INITIAL_FORMS": "0",
            "productotienda-MIN_NUM_FORMS": "0",
            "productotienda-MAX_NUM_FORMS": "1",
            "productotienda-0-publicado": "on",
            "productotienda-0-destacado": "",
            "productotienda-0-categoria": "",
            "productotienda-0-orden": "0",
            "productotienda-0-slug": "",
            "productotienda-0-titulo": "Camiseta de algodón",
            "productotienda-0-resumen": "",
            "productotienda-0-descripcion_larga": "",
            "productotienda-0-precio_web": "",
            "productotienda-0-precio_oferta": "",
            "productotienda-0-oferta_desde": "",
            "productotienda-0-oferta_hasta": "",
            "productotienda-0-peso": "",
            "_save": "Guardar",
        }
        respuesta = self.client.post(
            reverse("admin:sri_fe_producto_change", args=[producto.pk]),
            datos,
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Producto.objects.count(), 1)
        extension = ProductoTienda.de(producto)
        self.assertIsNotNone(extension)
        self.assertTrue(extension.publicado)
        self.assertEqual(extension.titulo, "Camiseta de algodón")
        self.assertEqual(extension.slug, "camiseta-de-algodon")


def peticion():
    """Una petición con sesión, para probar el carrito sin pasar por el navegador."""
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


class PruebasDelCarrito(TestCase):
    """El carrito vive en la sesión: suma, quita y no ofrece lo que ya no se vende."""

    def setUp(self):
        self.producto = crear_en_tienda(publicado=True, precio_web=Decimal("10.00"))
        self.otro = crear_en_tienda(
            codigo="P-002", descripcion="Otra cosa", publicado=True,
            precio_unitario=Decimal("5.00"),
        )

    def test_agregar_dos_veces_acumula(self):
        carrito = Carrito(peticion())
        carrito.agregar(self.producto, Decimal("2"))
        carrito.agregar(self.producto, Decimal("3"))
        self.assertEqual(carrito.cantidad_de(self.producto), Decimal("5"))
        self.assertEqual(carrito.unidades, Decimal("5"))

    def test_los_totales_llevan_el_iva(self):
        carrito = Carrito(peticion())
        carrito.agregar(self.producto, Decimal("2"))
        self.assertEqual(carrito.subtotal, Decimal("20.00"))
        self.assertEqual(carrito.iva, Decimal("3.00"))
        self.assertEqual(carrito.total, Decimal("23.00"))

    def test_fijar_en_cero_quita_la_linea(self):
        carrito = Carrito(peticion())
        carrito.agregar(self.producto, Decimal("2"))
        carrito.fijar(self.producto, Decimal("0"))
        self.assertTrue(carrito.vacio)

    def test_lo_que_se_despublica_se_cae_del_carrito(self):
        carrito = Carrito(peticion())
        carrito.agregar(self.producto, Decimal("1"))
        carrito.agregar(self.otro, Decimal("1"))
        self.producto.publicado = False
        self.producto.save()
        self.assertEqual([linea.producto for linea in carrito.lineas()], [self.otro])

    def test_lo_agotado_no_entra_en_el_carrito(self):
        Existencia.objects.create(producto=self.producto, cantidad=Decimal("0"))
        carrito = Carrito(peticion())
        carrito.agregar(self.producto, Decimal("1"))
        self.assertEqual(carrito.lineas(), [])


class PruebasDeLaLineaEnVivo(TestCase):
    """El carrito cambia la cantidad sin recargar y devuelve los importes."""

    def setUp(self):
        self.producto = crear_en_tienda(publicado=True, precio_web=Decimal("10.00"))

    def _fijar(self, cantidad, producto=None):
        return self.client.post(
            reverse("tienda:linea_carrito"),
            {"producto": (producto or self.producto).pk, "cantidad": cantidad},
        )

    def test_la_cantidad_se_guarda_y_vuelven_los_importes(self):
        respuesta = self._fijar("3")

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertFalse(datos["quitada"])
        self.assertEqual(datos["cantidad"], "3")
        self.assertEqual(datos["linea"], "34,50")
        self.assertEqual(datos["subtotal"], "30,00")
        self.assertEqual(datos["iva"], "4,50")
        self.assertEqual(datos["total"], "34,50")
        self.assertEqual(datos["unidades"], "3")
        self.assertFalse(datos["vacia"])
        self.assertEqual(self.client.session["carrito_tienda"], {str(self.producto.pk): "3"})

    def test_cambiar_la_cantidad_recalcula_el_total(self):
        self._fijar("2")
        datos = self._fijar("5").json()

        self.assertEqual(datos["cantidad"], "5")
        self.assertEqual(datos["linea"], "57,50")
        self.assertEqual(datos["total"], "57,50")
        self.assertEqual(self.client.session["carrito_tienda"], {str(self.producto.pk): "5"})

    def test_los_totales_suman_todas_las_lineas(self):
        otro = crear_en_tienda(
            codigo="P-002", descripcion="Otra cosa", publicado=True,
            precio_unitario=Decimal("5.00"),
        )
        self._fijar("1", otro)
        datos = self._fijar("2").json()

        self.assertEqual(datos["subtotal"], "25,00")   # 20 + 5
        self.assertEqual(datos["total"], "28,75")

    def test_cero_quita_la_linea(self):
        self._fijar("2")
        datos = self._fijar("0").json()

        self.assertTrue(datos["quitada"])
        self.assertTrue(datos["vacia"])
        self.assertEqual(datos["total"], "0,00")
        self.assertEqual(self.client.session["carrito_tienda"], {})

    def test_un_producto_que_ya_no_esta_no_se_toca(self):
        respuesta = self.client.post(
            reverse("tienda:linea_carrito"), {"producto": 999999, "cantidad": "1"}
        )

        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(respuesta.json()["ok"])

    def test_lo_agotado_no_se_puede_pedir(self):
        Existencia.objects.create(producto=self.producto, cantidad=Decimal("0"))

        respuesta = self._fijar("2")

        self.assertEqual(respuesta.status_code, 409)
        self.assertFalse(respuesta.json()["ok"])

    def test_solo_admite_el_envio_del_formulario(self):
        respuesta = self.client.get(reverse("tienda:linea_carrito"))

        self.assertEqual(respuesta.status_code, 405)

    def test_sin_javascript_queda_el_formulario_de_siempre(self):
        self.client.post(
            reverse("tienda:agregar"), {"producto": self.producto.pk, "cantidad": "1"}
        )

        respuesta = self.client.get(reverse("tienda:carrito"))

        self.assertContains(respuesta, "data-carrito")
        self.assertContains(respuesta, "Actualizar cantidades")


class PruebasDeLaFichaConOferta(TestCase):
    """La ficha dice cuál es el precio normal y cuál el de oferta."""

    def setUp(self):
        self.producto = crear_en_tienda(
            publicado=True,
            precio_web=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
        )

    def test_la_ficha_ensena_los_dos_precios(self):
        respuesta = self.client.get(
            reverse("tienda:producto", args=[self.producto.slug])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Precio normal")
        self.assertContains(respuesta, "Precio de oferta")
        self.assertContains(respuesta, "23,00")   # el de antes, con IVA
        self.assertContains(respuesta, "17,25")   # el de la oferta, con IVA

    def test_sin_oferta_solo_hay_un_precio(self):
        self.producto.precio_oferta = None
        self.producto.save()

        respuesta = self.client.get(
            reverse("tienda:producto", args=[self.producto.slug])
        )

        self.assertNotContains(respuesta, "Precio de oferta")


class PruebasDelLogoDeLaEmpresa(TestCase):
    """La tienda es del negocio: lleva su logo, no el de la aplicación."""

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

    def setUp(self):
        from configuracion.models import LogoEmisor
        from factec.django.models import ConfiguracionEmisor

        self.producto = crear_en_tienda(publicado=True)
        self.emisor = ConfiguracionEmisor.objects.create(
            nombre="Principal",
            activo=True,
            ambiente=1,
            ruc="0703886697001",
            razon_social="URDIN GONZALEZ JOHNNY EDGAR",
            nombre_comercial="ORVIQUE",
            dir_matriz="PANAMERICANA Y CARCHI",
            estab="001",
            pto_emi="001",
        )
        self.logo = LogoEmisor.objects.create(
            emisor=self.emisor,
            imagen=SimpleUploadedFile("empresa.png", b"\x89PNG\r\n\x1a\n"),
        )

    def test_la_cabecera_lleva_el_logo_de_la_empresa(self):
        respuesta = self.client.get(reverse("tienda:portada"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.logo.url)
        self.assertContains(respuesta, 'alt="ORVIQUE"')

    def test_el_pie_lleva_el_nombre_del_negocio_no_el_de_la_persona(self):
        respuesta = self.client.get(reverse("tienda:portada"))

        self.assertContains(respuesta, "ORVIQUE")
        self.assertNotContains(respuesta, "URDIN GONZALEZ JOHNNY EDGAR")

    def test_sin_logo_propio_la_tienda_sigue_saliendo(self):
        self.logo.delete()

        respuesta = self.client.get(reverse("tienda:portada"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "/media/logos/")


class PruebasDeLaTiendaPublica(TestCase):
    """El catálogo que ve cualquiera y el pedido que deja."""

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Ropa")
        self.producto = crear_en_tienda(
            publicado=True, categoria=self.categoria, precio_web=Decimal("10.00")
        )
        self.oculto = crear_en_tienda(
            codigo="P-002", descripcion="Lo que no se publicó", publicado=False
        )

    def test_la_portada_enseña_solo_lo_publicado(self):
        respuesta = self.client.get("/tienda/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.producto.nombre)
        self.assertNotContains(respuesta, "Lo que no se publicó")

    def test_la_categoria_enseña_sus_productos(self):
        respuesta = self.client.get(f"/tienda/c/{self.categoria.slug}/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.producto.nombre)

    def test_la_ficha_de_lo_no_publicado_no_existe(self):
        respuesta = self.client.get(f"/tienda/p/{self.oculto.slug}/")
        self.assertEqual(respuesta.status_code, 404)

    def test_agregar_deja_el_producto_en_la_sesion(self):
        respuesta = self.client.post(
            "/tienda/carrito/agregar/",
            {"producto": self.producto.pk, "cantidad": "2", "seguir": "1"},
        )
        self.assertRedirects(respuesta, f"/tienda/p/{self.producto.slug}/")
        self.assertEqual(
            Decimal(self.client.session["carrito_tienda"][str(self.producto.pk)]),
            Decimal("2"),
        )

    def test_el_pedido_se_crea_con_la_cedula_y_vacia_el_carrito(self):
        self.client.post(
            "/tienda/carrito/agregar/", {"producto": self.producto.pk, "cantidad": "2"}
        )
        respuesta = self.client.post(
            "/tienda/confirmar/",
            {
                "nombre": "Ana Pérez",
                "identificacion": "1710034065",
                "email": "ana@example.com",
                "telefono": "0999999999",
                "direccion": "Av. Siempre Viva 123",
                "nota": "Entregar por la tarde",
            },
        )

        pedido = Pedido.objects.get()
        self.assertRedirects(respuesta, f"/tienda/gracias/{pedido.referencia}/")
        self.assertEqual(pedido.lineas.count(), 1)
        self.assertEqual(pedido.subtotal, Decimal("20.00"))
        self.assertEqual(pedido.iva, Decimal("3.00"))
        self.assertEqual(pedido.total, Decimal("23.00"))
        self.assertEqual(pedido.cliente.tipo_identificacion, "05")
        self.assertEqual(pedido.cliente.identificacion, "1710034065")
        self.assertEqual(pedido.nombre, "Ana Pérez")
        self.assertEqual(self.client.session["carrito_tienda"], {})

    def test_sin_identificacion_la_factura_va_a_consumidor_final(self):
        self.client.post(
            "/tienda/carrito/agregar/", {"producto": self.producto.pk, "cantidad": "1"}
        )
        self.client.post("/tienda/confirmar/", {"nombre": "Quien sea"})

        pedido = Pedido.objects.get()
        self.assertEqual(pedido.cliente.identificacion, Cliente.CONSUMIDOR_FINAL)
        self.assertEqual(pedido.cliente.tipo_identificacion, "07")

    def test_una_identificacion_mal_escrita_no_crea_el_pedido(self):
        self.client.post(
            "/tienda/carrito/agregar/", {"producto": self.producto.pk, "cantidad": "1"}
        )
        respuesta = self.client.post(
            "/tienda/confirmar/", {"nombre": "Ana", "identificacion": "123"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertIn("identificacion", respuesta.context["formulario"].errors)

    def test_el_acuse_se_ve_por_la_referencia(self):
        self.client.post(
            "/tienda/carrito/agregar/", {"producto": self.producto.pk, "cantidad": "1"}
        )
        self.client.post("/tienda/confirmar/", {"nombre": "Ana"})
        pedido = Pedido.objects.get()

        respuesta = self.client.get(f"/tienda/gracias/{pedido.referencia}/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, pedido.numero)


class PruebasDeLosPedidos(TestCase):
    """La pantalla de pedidos y el paso a la factura."""

    def setUp(self):
        User.objects.create_user("quien-lleva-la-tienda", password="clave")
        self.client.force_login(User.objects.get(username="quien-lleva-la-tienda"))
        self.producto = crear_en_tienda(publicado=True, precio_web=Decimal("10.00"))
        self.pedido = Pedido.objects.create(
            nombre="Ana Pérez", identificacion="1710034065",
            cliente=Cliente.objects.create(
                razon_social="Ana Pérez", identificacion="1710034065",
                tipo_identificacion="05",
            ),
        )
        LineaPedido.objects.create(
            pedido=self.pedido, producto=self.producto,
            codigo=self.producto.codigo_principal, descripcion=self.producto.nombre,
            cantidad=Decimal("2"), precio_unitario=Decimal("10.00"), tarifa_iva=Decimal("15.00"),
        )
        self.pedido.calcular_totales()
        self.pedido.save()

    def test_sin_sesion_no_se_entra(self):
        self.client.logout()
        respuesta = self.client.get("/tienda/pedidos/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/entrar/", respuesta["Location"])

    def test_la_lista_y_el_detalle_cargan(self):
        lista = self.client.get("/tienda/pedidos/")
        detalle = self.client.get(f"/tienda/pedidos/{self.pedido.pk}/")
        self.assertEqual(lista.status_code, 200)
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(lista, self.pedido.numero)

    def test_facturar_arma_la_factura_con_sus_lineas(self):
        respuesta = self.client.post(f"/tienda/pedidos/{self.pedido.pk}/facturar/")

        self.pedido.refresh_from_db()
        self.assertIsNotNone(self.pedido.factura_id)
        factura = self.pedido.factura
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], f"/facturar/{factura.pk}/")
        self.assertEqual(factura.detalles.count(), 1)
        self.assertEqual(factura.receptor, self.pedido.cliente)
        self.assertEqual(factura.detalles.first().precio_unitario, Decimal("10.00"))
        self.assertIn(self.pedido.numero, factura.observaciones)

    def test_facturar_dos_veces_no_duplica(self):
        self.client.post(f"/tienda/pedidos/{self.pedido.pk}/facturar/")
        self.client.post(f"/tienda/pedidos/{self.pedido.pk}/facturar/")
        self.assertEqual(Factura.objects.count(), 1)
        self.assertEqual(Pedido.objects.get(pk=self.pedido.pk).factura.detalles.count(), 1)

    def test_un_pedido_anulado_no_se_factura(self):
        self.pedido.anulado = True
        self.pedido.save()
        self.client.post(f"/tienda/pedidos/{self.pedido.pk}/facturar/")
        self.pedido.refresh_from_db()
        self.assertIsNone(self.pedido.factura_id)

    def test_se_puede_anular_mientras_no_tenga_factura(self):
        respuesta = self.client.post(f"/tienda/pedidos/{self.pedido.pk}/anular/")
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertTrue(self.pedido.anulado)

    def test_la_opcion_del_menu_existe(self):
        from personalize_options.models import Opcion

        opcion = Opcion.objects.get(clave="pedidos")
        self.assertTrue(opcion.en_menu)
        self.assertEqual(opcion.url, "/tienda/pedidos/")
        # La tienda tiene su apartado, después de Catálogo.
        self.assertEqual(opcion.grupo, "Tienda")
        self.assertGreater(opcion.categoria.orden, 40)   # Catálogo
        self.assertLess(opcion.categoria.orden, 45)      # Caja


class PruebasDeLasCategorias(TestCase):
    """Las categorías se crean y se corrigen desde la aplicación."""

    def setUp(self):
        User.objects.create_user("quien-lleva-la-tienda", password="clave")
        self.client.force_login(User.objects.get(username="quien-lleva-la-tienda"))

    def test_sin_sesion_no_se_entra(self):
        self.client.logout()
        respuesta = self.client.get("/tienda/categorias/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/entrar/", respuesta["Location"])

    def test_la_pantalla_lista_las_categorias(self):
        Categoria.objects.create(nombre="Ropa")
        respuesta = self.client.get("/tienda/categorias/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ropa")

    def test_se_crea_una_categoria(self):
        respuesta = self.client.post(
            "/tienda/categorias/nueva/",
            {"nombre": "Ropa de niño", "padre": "", "descripcion": "", "orden": "0",
             "activa": "on", "slug": ""},
        )
        self.assertRedirects(respuesta, "/tienda/categorias/")
        categoria = Categoria.objects.get()
        self.assertEqual(categoria.nombre, "Ropa de niño")
        self.assertEqual(categoria.slug, "ropa-de-nino")
        self.assertTrue(categoria.activa)

    def test_no_se_puede_colgar_de_su_hija(self):
        ropa = Categoria.objects.create(nombre="Ropa")
        camisetas = Categoria.objects.create(nombre="Camisetas", padre=ropa)

        respuesta = self.client.post(
            f"/tienda/categorias/{ropa.pk}/",
            {"nombre": "Ropa", "padre": camisetas.pk, "descripcion": "", "orden": "0",
             "activa": "on", "slug": ropa.slug},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("padre", respuesta.context["formulario"].errors)
        ropa.refresh_from_db()
        self.assertIsNone(ropa.padre_id)

    def test_la_opcion_del_menu_existe(self):
        from personalize_options.models import Opcion

        opcion = Opcion.objects.get(clave="categorias_tienda")
        self.assertEqual(opcion.grupo, "Tienda")
        self.assertEqual(opcion.url, "/tienda/categorias/")
        self.assertLess(opcion.orden, Opcion.objects.get(clave="pedidos").orden)


class PruebasDelListado(TestCase):
    """El buscador, los filtros y el orden de los listados."""

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Todo")
        self.barato = crear_en_tienda(
            codigo="P-001", descripcion="Mouse barato", publicado=True,
            categoria=self.categoria, precio_unitario=Decimal("10.00"),
        )
        self.caro = crear_en_tienda(
            codigo="P-002", descripcion="Teclado caro", publicado=True,
            categoria=self.categoria, precio_unitario=Decimal("50.00"),
        )
        self.en_oferta = crear_en_tienda(
            codigo="P-003", descripcion="Producto con descuento", publicado=True,
            categoria=self.categoria, precio_unitario=Decimal("20.00"),
            precio_oferta=Decimal("15.00"),
        )

    def _categoria(self, **filtros):
        return self.client.get("/tienda/c/todo/", filtros)

    def test_la_busqueda_encuentra_por_nombre(self):
        respuesta = self.client.get("/tienda/buscar/", {"q": "mouse"})
        self.assertContains(respuesta, "Mouse barato")
        self.assertNotContains(respuesta, "Teclado caro")

    def test_el_orden_por_precio(self):
        menor = self._categoria(orden="menor")
        mayor = self._categoria(orden="mayor")
        self.assertEqual(
            [p.nombre for p in menor.context["productos"]],
            ["Mouse barato", "Producto con descuento", "Teclado caro"],
        )
        self.assertEqual(
            [p.nombre for p in mayor.context["productos"]],
            ["Teclado caro", "Producto con descuento", "Mouse barato"],
        )

    def test_el_filtro_de_precio_se_aplica_al_precio_con_iva(self):
        respuesta = self._categoria(min="15")
        self.assertCountEqual(
            [p.nombre for p in respuesta.context["productos"]],
            ["Producto con descuento", "Teclado caro"],
        )

    def test_el_filtro_de_oferta(self):
        respuesta = self._categoria(oferta="1")
        self.assertEqual(
            [p.nombre for p in respuesta.context["productos"]],
            ["Producto con descuento"],
        )

    def test_el_filtro_de_stock(self):
        Existencia.objects.create(producto=self.caro, cantidad=Decimal("0"))
        respuesta = self._categoria(stock="1")
        self.assertNotIn("Teclado caro", [p.nombre for p in respuesta.context["productos"]])

    def test_las_ofertas_son_las_que_estan_vigentes(self):
        respuesta = self.client.get("/tienda/ofertas/")
        nombres = [p.nombre for p in respuesta.context["productos"]]
        self.assertIn("Producto con descuento", nombres)
        self.assertNotIn("Mouse barato", nombres)

    def test_comprar_ahora_lleva_derecho_al_pedido(self):
        respuesta = self.client.post(
            "/tienda/carrito/agregar/",
            {"producto": self.barato.pk, "cantidad": "1", "comprar": "1"},
        )
        self.assertRedirects(respuesta, "/tienda/confirmar/")


class PruebasDelTextoEnriquecido(TestCase):
    """La descripción larga: Markdown que sale ya limpio a la ficha."""

    def test_el_markdown_se_convierte(self):
        from .texto import markdown_a_html

        html = markdown_a_html("**Oferta** y *nuevo*")
        self.assertIn("<strong>Oferta</strong>", html)
        self.assertIn("<em>nuevo</em>", html)

    def test_las_tablas_salen(self):
        from .texto import markdown_a_html

        html = markdown_a_html("| Talla | Precio |\n| --- | --- |\n| M | 10 |")
        self.assertIn("<table>", html)
        self.assertIn("<th>Talla</th>", html)

    def test_lo_que_no_es_texto_se_quita(self):
        from .texto import markdown_a_html

        html = markdown_a_html('Hola <script>alert("x")</script> **mundo**')
        self.assertNotIn("<script", html)
        self.assertNotIn("alert", html)
        self.assertIn("<strong>mundo</strong>", html)

    def test_los_estilos_y_los_guiones_se_van(self):
        from .texto import markdown_a_html

        html = markdown_a_html('<p style="color:red" onclick="malo()">Texto</p>')
        self.assertNotIn("style=", html)
        self.assertNotIn("onclick", html)

    def test_un_enlace_de_javascript_no_pasa(self):
        from .texto import markdown_a_html

        html = markdown_a_html("[pulse](javascript:alert(1))")
        self.assertNotIn("javascript:", html)

    def test_el_texto_vacio_no_arma_nada(self):
        from .texto import markdown_a_html

        self.assertEqual(markdown_a_html(""), "")
        self.assertEqual(markdown_a_html("   "), "")

    def test_el_producto_publica_la_descripcion_ya_formateada(self):
        producto = crear_en_tienda(
            publicado=True,
            descripcion_larga="## Materiales\n\n- Algodón\n- **Poliéster**",
        )
        self.assertIn("<h2>Materiales</h2>", producto.descripcion_html)
        self.assertIn("<li>Algodón</li>", producto.descripcion_html)

    def test_sin_descripcion_larga_no_hay_html(self):
        producto = crear_en_tienda(publicado=True)
        self.assertEqual(producto.descripcion_html, "")

    def test_la_ficha_enseña_la_descripcion_formateada(self):
        producto = crear_en_tienda(
            publicado=True,
            precio_web=Decimal("10.00"),
            descripcion_larga="| Talla | Precio |\n| --- | --- |\n| M | 10 |",
        )
        respuesta = self.client.get(f"/tienda/p/{producto.slug}/")
        self.assertContains(respuesta, "<table>")


class PruebasDeLasPreguntas(TestCase):
    """Lo que preguntan en la ficha y la respuesta del vendedor."""

    def setUp(self):
        self.producto = crear_en_tienda(
            publicado=True, precio_web=Decimal("10.00")
        )
        User.objects.create_user("quien-lleva-la-tienda", password="clave-de-prueba")
        self.gente = User.objects.get(username="quien-lleva-la-tienda")

    def test_sin_sesion_no_se_entra_a_la_pantalla(self):
        respuesta = self.client.get("/tienda/preguntas/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/entrar/", respuesta["Location"])

    def test_cualquiera_deja_una_pregunta(self):
        respuesta = self.client.post(
            f"/tienda/p/{self.producto.slug}/preguntar/",
            {"nombre": "Ana", "email": "ana@example.com", "texto": "¿Llega el lunes?"},
        )
        self.assertRedirects(respuesta, f"/tienda/p/{self.producto.slug}/")
        pregunta = Pregunta.objects.get()
        self.assertEqual(pregunta.nombre, "Ana")
        self.assertEqual(pregunta.producto, self.producto)
        self.assertFalse(pregunta.contestada)

    def test_la_pregunta_sin_responder_no_sale_en_la_ficha(self):
        Pregunta.objects.create(
            producto=self.producto, nombre="Ana", texto="¿Llega el lunes?"
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        self.assertNotContains(respuesta, "¿Llega el lunes?")

    def test_la_respondida_sale_con_su_respuesta(self):
        Pregunta.objects.create(
            producto=self.producto, nombre="Ana", texto="¿Llega el lunes?",
            respuesta="Sí, llega.", publicada=True,
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        self.assertContains(respuesta, "¿Llega el lunes?")
        self.assertContains(respuesta, "Sí, llega.")

    def test_la_oculta_no_sale_aunque_este_respondida(self):
        Pregunta.objects.create(
            producto=self.producto, nombre="Ana", texto="¿Llega el lunes?",
            respuesta="Sí, llega.", publicada=False,
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        self.assertNotContains(respuesta, "¿Llega el lunes?")

    def test_el_robot_que_llena_la_trampa_no_pasa(self):
        self.client.post(
            f"/tienda/p/{self.producto.slug}/preguntar/",
            {"nombre": "Ana", "texto": "Compra ya", "trampa": "spam"},
        )
        self.assertEqual(Pregunta.objects.count(), 0)

    def test_el_vendedor_responde(self):
        pregunta = Pregunta.objects.create(
            producto=self.producto, nombre="Ana", texto="¿Llega el lunes?"
        )
        self.client.force_login(self.gente)
        respuesta = self.client.post(
            f"/tienda/preguntas/{pregunta.pk}/responder/", {"respuesta": "Sí, el lunes."}
        )
        self.assertRedirects(respuesta, "/tienda/preguntas/")
        pregunta.refresh_from_db()
        self.assertTrue(pregunta.contestada)
        self.assertEqual(pregunta.respondida_por, self.gente)
        self.assertIsNotNone(pregunta.respondida)

    def test_una_respuesta_vacia_no_borra_la_anterior(self):
        pregunta = Pregunta.objects.create(
            producto=self.producto, nombre="Ana", texto="¿Llega?",
            respuesta="Sí, llega.",
        )
        self.client.force_login(self.gente)
        self.client.post(f"/tienda/preguntas/{pregunta.pk}/responder/", {"respuesta": "  "})
        pregunta.refresh_from_db()
        self.assertEqual(pregunta.respuesta, "Sí, llega.")

    def test_el_vendedor_oculta_y_vuelve_a_mostrar(self):
        pregunta = Pregunta.objects.create(
            producto=self.producto, nombre="Ana", texto="¿Llega?", respuesta="Sí"
        )
        self.client.force_login(self.gente)
        self.client.post(f"/tienda/preguntas/{pregunta.pk}/publicar/")
        pregunta.refresh_from_db()
        self.assertFalse(pregunta.publicada)
        self.client.post(f"/tienda/preguntas/{pregunta.pk}/publicar/")
        pregunta.refresh_from_db()
        self.assertTrue(pregunta.publicada)

    def test_la_pantalla_cuenta_las_que_faltan(self):
        Pregunta.objects.create(producto=self.producto, nombre="Ana", texto="Una")
        self.client.force_login(self.gente)
        respuesta = self.client.get("/tienda/preguntas/")
        self.assertEqual(respuesta.context["sin_responder"], 1)

    def test_las_opciones_del_menu_tienen_su_orden(self):
        from personalize_options.models import Opcion

        preguntas = Opcion.objects.get(clave="preguntas_tienda")
        resenas = Opcion.objects.get(clave="resenas_tienda")
        self.assertEqual(preguntas.grupo, "Tienda")
        self.assertEqual(preguntas.url, "/tienda/preguntas/")
        self.assertEqual(resenas.url, "/tienda/resenas/")
        self.assertLess(Opcion.objects.get(clave="pedidos").orden, preguntas.orden)
        self.assertLess(preguntas.orden, resenas.orden)


class PruebasDeLasResenas(TestCase):
    """Las opiniones con estrellas: esperan aprobación y forman el promedio."""

    def setUp(self):
        self.producto = crear_en_tienda(
            publicado=True, precio_web=Decimal("10.00")
        )
        User.objects.create_user("quien-lleva-la-tienda", password="clave-de-prueba")
        self.gente = User.objects.get(username="quien-lleva-la-tienda")

    def test_cualquiera_deja_una_resena_y_queda_por_aprobar(self):
        respuesta = self.client.post(
            f"/tienda/p/{self.producto.slug}/resenar/",
            {"nombre": "Ana", "calificacion": "4", "comentario": "Muy bueno"},
        )
        self.assertRedirects(respuesta, f"/tienda/p/{self.producto.slug}/")
        resena = Resena.objects.get()
        self.assertEqual(resena.calificacion, 4)
        self.assertFalse(resena.aprobada)

    def test_sin_calificacion_no_se_guarda(self):
        self.client.post(
            f"/tienda/p/{self.producto.slug}/resenar/",
            {"nombre": "Ana", "comentario": "Muy bueno"},
        )
        self.assertEqual(Resena.objects.count(), 0)

    def test_la_pendiente_no_sale_en_la_ficha(self):
        Resena.objects.create(
            producto=self.producto, nombre="Ana", calificacion=5,
            comentario="Excelente producto",
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        self.assertNotContains(respuesta, "Excelente producto")

    def test_la_aprobada_sale_con_sus_estrellas(self):
        Resena.objects.create(
            producto=self.producto, nombre="Ana", calificacion=4,
            comentario="Excelente producto", aprobada=True,
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        self.assertContains(respuesta, "Excelente producto")
        self.assertContains(respuesta, "★★★★☆")

    def test_el_promedio_sale_de_las_aprobadas(self):
        Resena.objects.create(
            producto=self.producto, nombre="Ana", calificacion=5,
            comentario="Uno", aprobada=True,
        )
        Resena.objects.create(
            producto=self.producto, nombre="Luis", calificacion=3,
            comentario="Dos", aprobada=True,
        )
        Resena.objects.create(
            producto=self.producto, nombre="Eva", calificacion=1,
            comentario="Tres", aprobada=False,
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        self.assertEqual(respuesta.context["promedio"], 4.0)
        self.assertEqual(len(respuesta.context["resenas"]), 2)

    def test_la_distribucion_cuenta_cada_nota(self):
        Resena.objects.create(
            producto=self.producto, nombre="Ana", calificacion=5,
            comentario="Uno", aprobada=True,
        )
        Resena.objects.create(
            producto=self.producto, nombre="Luis", calificacion=5,
            comentario="Dos", aprobada=True,
        )
        respuesta = self.client.get(f"/tienda/p/{self.producto.slug}/")
        filas = {fila["estrellas"]: fila for fila in respuesta.context["distribucion"]}
        self.assertEqual(filas[5]["cuantas"], 2)
        self.assertEqual(filas[5]["porcentaje"], 100)
        self.assertEqual(filas[1]["cuantas"], 0)

    def test_se_aprueba_y_se_retira(self):
        resena = Resena.objects.create(
            producto=self.producto, nombre="Ana", calificacion=5, comentario="Bueno"
        )
        self.client.force_login(self.gente)

        self.client.post(f"/tienda/resenas/{resena.pk}/moderar/", {"accion": "aprobar"})
        resena.refresh_from_db()
        self.assertTrue(resena.aprobada)

        self.client.post(f"/tienda/resenas/{resena.pk}/moderar/", {"accion": "retirar"})
        resena.refresh_from_db()
        self.assertFalse(resena.aprobada)

    def test_la_pantalla_cuenta_las_pendientes(self):
        Resena.objects.create(
            producto=self.producto, nombre="Ana", calificacion=5, comentario="Bueno"
        )
        self.client.force_login(self.gente)
        respuesta = self.client.get("/tienda/resenas/")
        self.assertEqual(respuesta.context["pendientes"], 1)
        self.assertEqual(respuesta.context["cuantas"], 1)


class PruebasDelSeguimientoDelPedido(TestCase):
    """El cliente consulta su pedido con el número y su correo o su cédula."""

    def setUp(self):
        self.producto = crear_en_tienda(publicado=True, precio_web=Decimal("10.00"))
        self.pedido = Pedido.objects.create(
            nombre="Ana Pérez", identificacion="1710034065",
            email="ana@example.com",
        )

    def test_la_pantalla_carga_sin_datos(self):
        respuesta = self.client.get("/tienda/seguimiento/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["buscado"])

    def test_con_el_correo_aparece_el_pedido(self):
        respuesta = self.client.get(
            "/tienda/seguimiento/",
            {"numero": self.pedido.numero, "contacto": "ana@example.com"},
        )
        self.assertEqual(respuesta.context["pedido"], self.pedido)

    def test_con_la_cedula_aparece_el_pedido(self):
        respuesta = self.client.get(
            "/tienda/seguimiento/", {"numero": self.pedido.numero, "contacto": "1710034065"}
        )
        self.assertEqual(respuesta.context["pedido"], self.pedido)

    def test_con_otro_contacto_no_aparece(self):
        respuesta = self.client.get(
            "/tienda/seguimiento/", {"numero": self.pedido.numero, "contacto": "otro@example.com"}
        )
        self.assertIsNone(respuesta.context["pedido"])

    def test_el_numero_se_escribe_como_sea(self):
        respuesta = self.client.get(
            "/tienda/seguimiento/", {"numero": "p-000001", "contacto": "ana@example.com"}
        )
        self.assertEqual(respuesta.context["pedido"], self.pedido)

    def test_sin_numero_no_se_busca(self):
        respuesta = self.client.get("/tienda/seguimiento/", {"contacto": "ana@example.com"})
        self.assertIsNone(respuesta.context["pedido"])


class PruebasDelEditorDeLaDescripcion(TestCase):
    """El campo enriquecido se anuncia solo para que el editor lo tome."""

    def setUp(self):
        User.objects.create_user("quien-lleva-la-tienda", password="clave-de-prueba")
        self.client.force_login(User.objects.get(username="quien-lleva-la-tienda"))

    def test_el_campo_lleva_la_marca_del_editor(self):
        producto = crear_producto()
        respuesta = self.client.get(f"/catalogos/productos/{producto.pk}/")
        self.assertContains(respuesta, "data-editor-markdown")

    def test_la_pantalla_carga_el_guion_del_editor(self):
        producto = crear_producto()
        respuesta = self.client.get(f"/catalogos/productos/{producto.pk}/")
        self.assertContains(respuesta, "js/editor_markdown.js")


class PruebasDeLasFotos(TestCase):
    """Las fotos se sueltan en un recuadro, sin perder el formulario de siempre."""

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

    def setUp(self):
        self.gente = User.objects.create_user("quien-lleva-la-tienda", "clave-de-prueba")
        self.client.force_login(self.gente)
        self.producto = crear_producto()

    def test_la_pantalla_trae_la_zona_de_soltar(self):
        respuesta = self.client.get(f"/catalogos/productos/{self.producto.pk}/")

        self.assertContains(respuesta, "data-fotos")
        self.assertContains(respuesta, "Arrastre las fotos o los videos aquí")
        self.assertContains(respuesta, "data-archivo")

    def test_la_ficha_de_la_tienda_pinta_el_video(self):
        """Un video del producto se ve en la galería, con controles para reproducirlo."""
        tienda = ProductoTienda.extender(self.producto)
        tienda.publicado = True
        tienda.save()
        ImagenProducto.objects.create(
            producto=tienda,
            imagen=SimpleUploadedFile("demo.mp4", b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4"),
            alt="El producto en movimiento",
            orden=0,
            es_video=True,
        )

        respuesta = self.client.get(f"/tienda/p/{tienda.slug}/")

        self.assertContains(respuesta, '<video id="foto-principal"')
        self.assertContains(respuesta, "demo.mp4")
        self.assertNotContains(respuesta, "Sin foto")

    def test_la_pantalla_carga_el_guion_de_las_fotos(self):
        respuesta = self.client.get(f"/catalogos/productos/{self.producto.pk}/")

        self.assertContains(respuesta, "js/fotos_producto.js")

    def test_sin_javascript_sigue_estando_el_campo_de_archivo(self):
        respuesta = self.client.get(f"/catalogos/productos/{self.producto.pk}/")

        # El input del formset no se toca: solo se esconde con JavaScript.
        self.assertContains(respuesta, 'type="file"')
        self.assertContains(respuesta, "TOTAL_FORMS")

    def test_una_foto_se_guarda_con_el_formulario(self):
        datos = {
            "tipo": self.producto.tipo,
            "codigo_principal": self.producto.codigo_principal,
            "descripcion": self.producto.descripcion,
            "unidad_medida": self.producto.unidad_medida or "UNIDAD",
            "precio_unitario": "10,00",
            "codigo_porcentaje_iva": self.producto.codigo_porcentaje_iva or "4",
            "activo": "on",
            "minimo": "0",
            "ubicacion": "",
            "publicado": "on",
            "orden": "0",
            "titulo": "",
            "resumen": "",
            "descripcion_larga": "",
            "precio_web": "",
            "precio_oferta": "",
            "oferta_desde": "",
            "oferta_hasta": "",
            "peso": "",
            "imagenes-TOTAL_FORMS": "1",
            "imagenes-INITIAL_FORMS": "0",
            "imagenes-0-alt": "De frente",
            "imagenes-0-orden": "0",
            "imagenes-0-imagen": SimpleUploadedFile(
                "frente.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"
            ),
        }

        self.client.post(f"/catalogos/productos/{self.producto.pk}/", datos)

        foto = ImagenProducto.objects.get(producto=self.producto)
        self.assertEqual(foto.alt, "De frente")
        self.assertEqual(foto.orden, 0)
        self.assertEqual(foto.imagen.name.rsplit(".", 1)[-1], "png")


class PruebasDeLoQueSeMiro(TestCase):
    """La portada recuerda lo último que se miró, como en un marketplace."""

    def setUp(self):
        self.primero = crear_en_tienda(
            codigo="P-101", descripcion="Primero", publicado=True, precio_web=Decimal("10.00")
        )
        self.segundo = crear_en_tienda(
            codigo="P-102", descripcion="Segundo", publicado=True, precio_web=Decimal("12.00")
        )

    def test_al_abrir_la_ficha_queda_en_la_sesion(self):
        self.client.get(f"/tienda/p/{self.primero.slug}/")
        self.assertEqual(self.client.session["vistos_tienda"], [self.primero.pk])

    def test_el_ultimo_va_primero_y_no_se_repite(self):
        self.client.get(f"/tienda/p/{self.primero.slug}/")
        self.client.get(f"/tienda/p/{self.segundo.slug}/")
        self.client.get(f"/tienda/p/{self.primero.slug}/")
        self.assertEqual(
            self.client.session["vistos_tienda"], [self.primero.pk, self.segundo.pk]
        )

    def test_la_portada_los_enseña(self):
        self.client.get(f"/tienda/p/{self.primero.slug}/")
        respuesta = self.client.get("/tienda/")
        self.assertIn(self.primero, respuesta.context["vistos"])

    def test_lo_que_se_despublica_ya_no_sale(self):
        self.client.get(f"/tienda/p/{self.primero.slug}/")
        self.primero.publicado = False
        self.primero.save(update_fields=["publicado"])
        respuesta = self.client.get("/tienda/")
        self.assertEqual(respuesta.context["vistos"], [])
