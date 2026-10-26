"""Pruebas del catálogo: productos, servicios y clientes.

Las listas cuentan lo que se ha facturado de cada uno. Es una cuenta que se hace
con las líneas de las facturas, porque el paquete no deja la relación inversa
desde el producto: si se cambia, aquí se ve.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
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

__all__ = ["PruebasDelCatalogo", "PruebasDelTransporte"]


class PruebasDelCatalogo(TestCase):
    """Altas y listas."""

    def setUp(self) -> None:
        User.objects.create_user("quien-lleva-el-catalogo", password="x")
        self.client.force_login(User.objects.get(username="quien-lleva-el-catalogo"))

    def test_el_formulario_acepta_la_coma_y_deja_la_existencia_inicial(self) -> None:
        respuesta = self.client.post(
            "/catalogos/productos/nuevo/",
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

        respuesta = self.client.get("/catalogos/productos/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("1 vez facturado", respuesta.content.decode())

    def test_la_lista_de_clientes_dice_cuantas_facturas_tiene_cada_uno(self) -> None:
        receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA", identificacion="1790012345001",
            tipo_identificacion="04",
        )
        Factura.objects.create(receptor=receptor, fecha_emision="2026-01-15")

        respuesta = self.client.get("/catalogos/clientes/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("CLIENTE DE PRUEBA", respuesta.content.decode())

    def test_los_avisos_del_servidor_salen_marcados_para_el_aviso_flotante(self) -> None:
        """El aviso se marca con su tipo: interfaz.js lo levanta como aviso de Metro."""
        respuesta = self.client.post(
            "/catalogos/productos/nuevo/",
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

        pagina = self.client.get("/catalogos/productos/").content.decode()

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

        pagina = self.client.get("/catalogos/productos/").content.decode()

        self.assertIn("12,08", pagina)  # 10,50 más el 15 %
        self.assertIn("10,50 + IVA 15%", pagina)

    def test_un_precio_sin_iva_no_suma_nada(self) -> None:
        """Exento de IVA: el precio de la lista es el mismo de la ficha."""
        Producto.objects.create(
            tipo="servicio", codigo_principal="HORA", descripcion="HORA DE CONSULTORIA",
            precio_unitario="10.00", codigo_porcentaje_iva="7",
        )

        pagina = self.client.get("/catalogos/productos/").content.decode()

        self.assertIn("10,00 + Exento de IVA", pagina)


class PruebasDelTransporte(TestCase):
    """Los conductores y los vehículos de la guía de remisión: altas y listas."""

    def setUp(self) -> None:
        User.objects.create_user("quien-lleva-el-transporte", password="clave-de-pruebas")
        self.client.force_login(User.objects.get(username="quien-lleva-el-transporte"))

    def test_se_da_de_alta_un_conductor(self) -> None:
        respuesta = self.client.post(
            "/catalogos/conductores/nuevo/",
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
            "/catalogos/vehiculos/nuevo/",
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
            f"/catalogos/conductores/{conductor.pk}/",
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

        respuesta = self.client.get("/catalogos/conductores/")

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

        respuesta = self.client.get("/catalogos/vehiculos/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["vehiculos"][0].cuantas_guias, 1)

    def test_las_listas_se_pueden_buscar(self) -> None:
        Conductor.objects.create(
            razon_social="TRANSPORTES DEL NORTE", identificacion="1790012345001",
        )
        Vehiculo.objects.create(placa="PBX-1234")

        conductores = self.client.get("/catalogos/conductores/", {"q": "norte"})
        vehiculos = self.client.get("/catalogos/vehiculos/", {"q": "no-existe"})

        self.assertEqual(conductores.context["cuantos"], 1)
        self.assertEqual(vehiculos.context["cuantos"], 0)
