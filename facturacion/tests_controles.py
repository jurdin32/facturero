"""Pruebas de los controles de Metro en las pantallas.

Metro no pinta nada solo: sus componentes se piden desde el HTML con un
`data-role` (y sus barras de progreso con las clases `progress`/`bar`). Si una
plantilla deja de pedirlos, la pantalla se queda sin el control y nadie se entera
hasta que se mira. Esto lo mira.
"""

from __future__ import annotations

import re
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from factec.django.documentos import Cliente, Factura, FacturaDetalle, Producto
from factec.django.models import ComprobanteEmitido, EstadoComprobante
from django.contrib.contenttypes.models import ContentType

from inventario.models import Existencia

from caja.servicios import abrir as abrir_caja

__all__ = ["PruebasDeLosControlesEnLasPantallas"]


class PruebasDeLosControlesEnLasPantallas(TestCase):
    def setUp(self) -> None:
        User.objects.create_user("revisor", password="clave-de-prueba")
        self.client.force_login(User.objects.get(username="revisor"))
        # Facturar exige la caja del turno abierta.
        abrir_caja(User.objects.get(username="revisor"))
        self.receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA",
            identificacion="1790012345001",
            tipo_identificacion="04",
        )
        self.producto = Producto.objects.create(
            tipo="producto",
            codigo_principal="CAJA-12",
            descripcion="CAJA DE DOCE",
            unidad_medida="CAJA",
            precio_unitario=Decimal("10.50"),
            codigo_porcentaje_iva="4",
        )
        self.factura = self._factura_autorizada()

    def _factura_autorizada(self) -> Factura:
        factura = Factura.objects.create(receptor=self.receptor, fecha_emision="2026-10-09")
        FacturaDetalle.objects.create(
            factura=factura, producto=self.producto, descripcion=self.producto.descripcion,
            cantidad=Decimal("2"), precio_unitario=self.producto.precio_unitario,
            unidad_medida=self.producto.unidad_medida,
        )
        comprobante = ComprobanteEmitido.objects.create(
            content_type=ContentType.objects.get_for_model(Factura),
            object_id=factura.pk,
            tipo_comprobante="01",
            ambiente=1,
            estab="001",
            pto_emi="001",
            secuencial="1",
            fecha_emision="2026-10-09",
            estado=EstadoComprobante.AUTORIZADO,
            razon_social_receptor=self.receptor.razon_social,
            identificacion_receptor=self.receptor.identificacion,
        )
        factura.comprobante = comprobante
        factura.save(update_fields=["comprobante"])
        return factura

    def _pagina(self, ruta: str) -> str:
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200, ruta)
        return respuesta.content.decode()

    # ------------------------------------------------------------ las listas

    def test_la_lista_de_facturas_usa_los_controles_de_metro(self) -> None:
        pagina = self._pagina("/wadmin/facturas/")
        # El buscador de texto lo pone Metro en la tabla; el formulario de arriba
        # solo lleva los filtros que el servidor necesita.
        self.assertIn("data-tabla", pagina)
        self.assertIn('data-role="select"', pagina)
        self.assertIn("data-prepend", pagina)
        # El estado, con el chip de Metro y no con un sello propio.
        self.assertIn('class="chip success soft"', pagina)
        self.assertNotIn("sello-", pagina)
        # El botón de la acción principal, con el color de la casa.
        self.assertIn('class="button primary"', pagina)

    def test_el_inventario_lleva_el_interruptor_de_reposicion(self) -> None:
        pagina = self._pagina("/wadmin/inventario/")
        self.assertIn('class="switch"', pagina)
        self.assertIn("data-enviar-al-cambiar", pagina)

    def test_las_listas_se_leen_como_un_listado(self) -> None:
        """Las cuatro listas van sin cabecera de columnas: una fila por registro,
        con su marca a la izquierda, lo esencial en medio y el dato a la derecha."""
        for ruta in (
            "/wadmin/facturas/",
            "/wadmin/catalogos/clientes/",
            "/wadmin/catalogos/productos/",
            "/wadmin/inventario/",
        ):
            with self.subTest(ruta=ruta):
                pagina = self._pagina(ruta)
                self.assertIn("listado", pagina, ruta)
                self.assertIn('class="col-marca"', pagina)
                self.assertIn('class="col-principal"', pagina)
                self.assertIn('class="col-dato"', pagina)

    # ---------------------------------------------------------- el tablero

    def test_el_tablero_lleva_las_barras_de_progreso(self) -> None:
        pagina = self._pagina("/wadmin/")
        self.assertIn("progress-component", pagina)
        self.assertIn('class="bar"', pagina)
        # Autorizadas sobre emitidas: una de una, o sea el 100 %.
        self.assertIn("100 %", pagina)

    def test_el_tablero_tiene_el_grafico_de_lo_que_mas_se_mueve(self) -> None:
        """Con su puesto, su barra y sus cuentas: la tarjeta de los últimos
        comprobantes se quitó para dejar sitio a este gráfico."""
        from factec.sri.fechas import hoy_en_ecuador

        factura = Factura.objects.create(
            receptor=self.receptor, fecha_emision=hoy_en_ecuador()
        )
        factura.detalles.create(
            descripcion=self.producto.descripcion,
            cantidad=Decimal("3"),
            precio_unitario=self.producto.precio_unitario,
        )

        pagina = self._pagina("/wadmin/")

        self.assertIn("Productos y servicios con más movimiento", pagina)
        self.assertIn('class="ranking"', pagina)
        self.assertIn("ranking-barra", pagina)
        self.assertIn(self.producto.descripcion, pagina)
        self.assertNotIn("Últimos comprobantes", pagina)

    def test_el_tablero_cuenta_las_autorizadas_sobre_las_emitidas(self) -> None:
        from facturacion import tablero as consultas

        hoy, _ = consultas.hoy_y_ayer()
        autorizadas = consultas.contadores(hoy)["autorizadas"]
        self.assertEqual(autorizadas["cuantas"], 1)
        self.assertEqual(autorizadas["emitidas"], 1)
        self.assertEqual(autorizadas["porcentaje"], 100)

    def test_el_tablero_dice_cuantos_van_en_marcha(self) -> None:
        from facturacion import tablero as consultas

        ComprobanteEmitido.objects.filter(pk=self.factura.comprobante.pk).update(
            estado=EstadoComprobante.RECIBIDO
        )
        hoy, _ = consultas.hoy_y_ayer()
        self.assertEqual(consultas.contadores(hoy)["por_resolver"]["en_marcha"], 1)

    # ------------------------------------------------- la ficha del comprobante

    def test_la_ficha_ensena_el_ciclo_del_comprobante(self) -> None:
        pagina = self._pagina(f"/wadmin/factura/{self.factura.pk}/")
        self.assertIn('class="progress-component exito"', pagina)
        self.assertIn('aria-valuenow="100"', pagina)
        self.assertIn("Firmada", pagina)
        self.assertIn("Autorizada", pagina)

    def test_la_ficha_avisa_cuando_va_por_el_sri(self) -> None:
        """Un comprobante en trámite gira, para que se vea que se está en ello."""
        ComprobanteEmitido.objects.filter(pk=self.factura.comprobante.pk).update(
            estado=EstadoComprobante.EN_PROCESO
        )
        pagina = self._pagina(f"/wadmin/factura/{self.factura.pk}/")
        self.assertIn('class="progress-component cuidado"', pagina)
        self.assertIn('aria-valuenow="80"', pagina)
        self.assertIn("activity-bars", pagina)

    def test_la_ficha_de_un_comprobante_devuelto_lo_dice_y_deja_reintentar(self) -> None:
        ComprobanteEmitido.objects.filter(pk=self.factura.comprobante.pk).update(
            estado=EstadoComprobante.DEVUELTO
        )
        pagina = self._pagina(f"/wadmin/factura/{self.factura.pk}/")
        self.assertIn('class="progress-component peligro"', pagina)
        self.assertIn("Reintentar el envío", pagina)
        self.assertIn('class="button warning"', pagina)

    # ---------------------------------------------------------- los formularios

    def test_el_formulario_de_producto_usa_los_controles_de_metro(self) -> None:
        pagina = self._pagina("/wadmin/catalogos/productos/nuevo/")
        self.assertIn('data-role="select"', pagina)
        self.assertIn('data-role="input"', pagina)
        # La casilla del tipo de producto y la del IVA llevan su icono delante.
        self.assertIn("mif-cube", pagina)
        self.assertIn("mif-percent", pagina)
        # Y el interruptor de «se puede facturar», que es un switch de Metro.
        self.assertIn('class="switch"', pagina)

    def test_el_formulario_de_facturar_usa_los_controles_de_metro(self) -> None:
        pagina = self._pagina("/wadmin/facturar/")
        self.assertIn('data-role="textarea"', pagina)
        self.assertIn('data-role="select"', pagina)
        self.assertIn('data-role="input"', pagina)
        # El botón que emite, con su color y su icono.
        self.assertIn('value="emitir"', pagina)
        self.assertIn("mif-send", pagina)

    def test_las_existencias_traen_su_barra(self) -> None:
        """Un bien con mínimo enseña lo que queda respecto a lo que se quiere."""
        Existencia.objects.create(producto=self.producto, cantidad=Decimal("5"), minimo=Decimal("10"))
        pagina = self._pagina("/wadmin/inventario/")
        self.assertIn("stock-celda", pagina)
        self.assertIn('aria-valuenow="25"', pagina)
        self.assertIn('class="progress-component cuidado"', pagina)

    # -------------------------------------------------------------- los iconos

    def test_los_iconos_que_piden_las_pantallas_estan_en_la_fuente(self) -> None:
        """Un nombre de icono que la fuente no trae deja la caja vacía.

        La fuente de iconos se pide con la clase (`mif-cube`) y sólo dibuja lo que
        tiene: con un nombre mal escrito —o inventado, como el de una opción nueva
        escrita a mano— la caja se queda en blanco y nadie se entera hasta que se
        mira la pantalla. Esto mira que todo lo que piden las pantallas exista.
        """
        fuente = (settings.BASE_DIR / "static/icons/core/style.css").read_text(encoding="utf-8")
        dibujados = set(re.findall(r"\.mif-([a-z0-9-]+):before", fuente))

        rutas = [
            "/wadmin/", "/wadmin/facturas/", "/wadmin/facturar/", "/wadmin/inventario/", "/wadmin/catalogos/clientes/",
            "/wadmin/catalogos/clientes/nuevo/", "/wadmin/catalogos/productos/nuevo/",
            "/wadmin/catalogos/conductores/nuevo/", "/wadmin/catalogos/vehiculos/nuevo/",
            "/wadmin/comprobantes/retenciones/", "/wadmin/comprobantes/retenciones/nuevo/",
            "/wadmin/comprobantes/guias-remision/nuevo/", "/wadmin/seguridad/", "/wadmin/seguridad/roles/nuevo/",
            "/wadmin/seguridad/usuarios/", "/wadmin/seguridad/opciones/", "/wadmin/seguridad/opciones/nueva/",
            "/wadmin/tienda/categorias/", "/wadmin/tienda/pedidos/", "/wadmin/tienda/preguntas/",
            "/wadmin/tienda/resenas/",
        ]
        pedidos: set[str] = set()

        # Los iconos de las opciones salen de la base de datos: se piden con
        # `mif-{{ icono }}` y no aparecen escritos en ninguna plantilla, así que
        # hay que mirarlos aparte.
        from personalize_options.models import Opcion

        for icono in Opcion.objects.exclude(icono="").values_list("icono", flat=True):
            pedidos.add(icono)

        for ruta in rutas:
            pedidos.update(re.findall(r"mif-([a-z0-9-]+)", self._pagina(ruta)))
        # La entrada se mira sin sesión, que con sesión manda al tablero.
        entrada = Client().get("/wadmin/entrar/")
        pedidos.update(re.findall(r"mif-([a-z0-9-]+)", entrada.content.decode()))

        self.assertEqual(sorted(pedidos - dibujados), [], "iconos que la fuente no tiene")
