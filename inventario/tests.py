"""Pruebas del inventario.

La regla es una sola: la existencia siempre es la suma del libro de movimientos.
Si eso cuadra, el inventario se puede creer.
"""

from __future__ import annotations

from decimal import Decimal

from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from factec.django.documentos import Cliente, Factura, FacturaDetalle, Producto
from factec.django.models import ComprobanteEmitido, EstadoComprobante

from .models import Existencia, Movimiento, TipoMovimiento, cantidad_total
from .servicios import descontar_de_la_factura, facturas_sin_descontar, quedaron_en_negativo

__all__ = ["PruebasDelInventario", "PruebasDelDescuentoAlFacturar"]


def factura_autorizada(producto, cantidad="3", receptor=None) -> Factura:
    """Una factura con comprobante autorizado, para probar el descuento."""
    receptor = receptor or Cliente.objects.create(
        razon_social="CLIENTE DE PRUEBA", identificacion="1790012345001",
        tipo_identificacion="04",
    )
    factura = Factura.objects.create(receptor=receptor, fecha_emision="2026-10-09")
    FacturaDetalle.objects.create(
        factura=factura, producto=producto, descripcion=producto.descripcion,
        cantidad=Decimal(cantidad), precio_unitario=producto.precio_unitario,
        unidad_medida=producto.unidad_medida,
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
        razon_social_receptor=receptor.razon_social,
        identificacion_receptor=receptor.identificacion,
    )
    factura.comprobante = comprobante
    factura.save(update_fields=["comprobante"])
    return factura


class PruebasDelInventario(TestCase):
    """Entradas, salidas y ajustes sobre un bien."""

    def setUp(self) -> None:
        User.objects.create_user("quien-mueve", password="x")
        self.client.force_login(User.objects.get(username="quien-mueve"))
        self.bien = Producto.objects.create(
            tipo="producto",
            codigo_principal="CAJA-12",
            descripcion="CAJA DE DOCE",
            unidad_medida="CAJA",
            precio_unitario="10.50",
        )
        self.servicio = Producto.objects.create(
            tipo="servicio",
            codigo_principal="HORA",
            descripcion="HORA DE CONSULTORIA",
            unidad_medida="HORA",
            precio_unitario="25",
        )

    def _mover(self, tipo: str, cantidad: str, **extra) -> Movimiento:
        return Movimiento.objects.create(
            producto=self.bien, fecha="2026-01-15", tipo=tipo, cantidad=Decimal(cantidad), **extra
        )

    # ---------------------------------------------------------------- pruebas

    def test_la_existencia_es_la_suma_del_libro(self) -> None:
        self._mover(TipoMovimiento.ENTRADA.value, "10")
        self._mover(TipoMovimiento.SALIDA.value, "3")

        existencia = Existencia.objects.get(producto=self.bien)

        self.assertEqual(existencia.cantidad, Decimal("7"))
        self.assertEqual(cantidad_total(self.bien), Decimal("7"))

    def test_un_ajuste_lleva_su_signo(self) -> None:
        self._mover(TipoMovimiento.ENTRADA.value, "10")
        self._mover(TipoMovimiento.AJUSTE.value, "-2")

        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("8"))
        self.assertEqual(cantidad_total(self.bien), Decimal("8"))

    def test_anular_un_movimiento_devuelve_la_cantidad(self) -> None:
        self._mover(TipoMovimiento.ENTRADA.value, "10")
        salida = self._mover(TipoMovimiento.SALIDA.value, "4")

        salida.delete()

        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("10"))
        self.assertEqual(cantidad_total(self.bien), Decimal("10"))

    def test_un_servicio_no_lleva_inventario(self) -> None:
        movimiento = Movimiento(
            producto=self.servicio, fecha="2026-01-15", tipo=TipoMovimiento.ENTRADA.value,
            cantidad=Decimal("1"),
        )

        with self.assertRaises(ValidationError):
            movimiento.full_clean()

    def test_el_aviso_de_reposicion_sale_del_minimo(self) -> None:
        existencia = Existencia.objects.create(producto=self.bien, cantidad=Decimal("2"))
        existencia.minimo = Decimal("5")
        existencia.save()

        self.assertTrue(Existencia.objects.get(producto=self.bien).bajo_minimo)

    def test_la_pantalla_del_inventario_avisa_de_lo_que_hay_que_reponer(self) -> None:
        Existencia.objects.create(producto=self.bien, cantidad=Decimal("2"), minimo=Decimal("5"))

        respuesta = self.client.get("/wadmin/inventario/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("CAJA DE DOCE", respuesta.content.decode())
        self.assertIn("stock-bajo", respuesta.content.decode())


    def test_el_libro_pide_confirmacion_antes_de_anular(self) -> None:
        """Anular devuelve la cantidad: la pantalla lo pregunta con un diálogo."""
        self._mover(TipoMovimiento.ENTRADA.value, "10")

        pagina = self.client.get(f"/wadmin/inventario/producto/{self.bien.pk}/").content.decode()

        self.assertIn("data-confirmar=", pagina)
        self.assertIn('data-titulo="Anular el movimiento"', pagina)

class PruebasDelDescuentoAlFacturar(TestCase):
    """Al autorizarse una factura, lo que va en ella sale del inventario."""

    def setUp(self) -> None:
        User.objects.create_user("quien-factura", password="x")
        self.quien = User.objects.get(username="quien-factura")
        self.bien = Producto.objects.create(
            tipo="producto", codigo_principal="CAJA-12", descripcion="CAJA DE DOCE",
            unidad_medida="CAJA", precio_unitario="10.50",
        )
        self.servicio = Producto.objects.create(
            tipo="servicio", codigo_principal="HORA", descripcion="HORA DE CONSULTORIA",
            unidad_medida="HORA", precio_unitario="25",
        )
        Movimiento.objects.create(
            producto=self.bien, fecha="2026-10-01", tipo=TipoMovimiento.ENTRADA.value,
            cantidad=Decimal("10"),
        )

    def test_la_factura_autorizada_descuenta_lo_que_lleva(self) -> None:
        factura = factura_autorizada(self.bien, cantidad="3")

        creados = descontar_de_la_factura(factura, usuario=self.quien)

        self.assertEqual(len(creados), 1)
        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("7"))
        self.assertEqual(cantidad_total(self.bien), Decimal("7"))
        self.assertEqual(creados[0].comprobante, factura.comprobante)

    def test_no_se_descuenta_dos_veces_la_misma_factura(self) -> None:
        factura = factura_autorizada(self.bien, cantidad="3")

        descontar_de_la_factura(factura)
        segunda = descontar_de_la_factura(factura)

        self.assertEqual(segunda, [])
        self.assertEqual(Movimiento.objects.filter(comprobante=factura.comprobante).count(), 1)
        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("7"))

    def test_un_borrador_no_descuenta_nada(self) -> None:
        receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA", identificacion="1790012345001",
            tipo_identificacion="04",
        )
        factura = Factura.objects.create(receptor=receptor, fecha_emision="2026-10-09")
        FacturaDetalle.objects.create(
            factura=factura, producto=self.bien, descripcion="CAJA DE DOCE",
            cantidad=Decimal("3"), precio_unitario=Decimal("10.50"),
        )

        self.assertEqual(descontar_de_la_factura(factura), [])
        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("10"))

    def test_los_servicios_no_se_descuentan(self) -> None:
        factura = factura_autorizada(self.servicio, cantidad="4")

        self.assertEqual(descontar_de_la_factura(factura), [])

    def test_con_el_descuento_apagado_no_se_mueve_nada(self) -> None:
        from personalize_options import ajustes

        factura = factura_autorizada(self.bien, cantidad="3")

        with ajustes.usar(inventario_descontar_al_facturar=False):
            self.assertEqual(descontar_de_la_factura(factura), [])

        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("10"))

    def test_el_libro_lleva_de_vuelta_a_la_factura(self) -> None:
        """En el libro, la serie que dejó el movimiento lleva a su factura."""
        self.client.force_login(self.quien)
        factura = factura_autorizada(self.bien, cantidad="3")
        descontar_de_la_factura(factura)

        respuesta = self.client.get(f"/wadmin/inventario/producto/{self.bien.pk}/")
        cuerpo = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(f'href="/wadmin/factura/{factura.pk}/"', cuerpo)
        self.assertIn("001-001-1", cuerpo)

    def test_avisa_cuando_el_bien_se_queda_en_negativo(self) -> None:
        factura = factura_autorizada(self.bien, cantidad="14")

        creados = descontar_de_la_factura(factura)

        self.assertEqual(len(quedaron_en_negativo(creados)), 1)
        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("-4"))

    def test_el_comando_recoge_lo_que_quedo_sin_descontar(self) -> None:
        """Lo emitido por el worker no pasa por la pantalla: el comando lo recoge."""
        factura = factura_autorizada(self.bien, cantidad="3")
        self.assertEqual([f.pk for f in facturas_sin_descontar()], [factura.pk])

        call_command("descontar_inventario")

        self.assertEqual(facturas_sin_descontar().count(), 0)
        self.assertEqual(Existencia.objects.get(producto=self.bien).cantidad, Decimal("7"))

    def test_el_comando_simulado_no_toca_el_inventario(self) -> None:
        factura_autorizada(self.bien, cantidad="3")

        call_command("descontar_inventario", "--simular")

        self.assertEqual(Movimiento.objects.filter(tipo=TipoMovimiento.FACTURA.value).count(), 0)
