"""Pruebas de la caja por usuario."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from . import servicios
from .models import MovimientoCaja, SesionCaja


class CajaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="cajero", password="secreto"
        )

    def test_una_sola_caja_abierta_por_usuario(self):
        sesion = servicios.abrir(self.usuario, Decimal("100.00"))
        self.assertTrue(sesion.abierta)
        self.assertEqual(servicios.sesion_abierta(self.usuario).pk, sesion.pk)
        with self.assertRaises(ValidationError):
            servicios.abrir(self.usuario, Decimal("0"))

    def test_movimientos_y_cierre_con_diferencia(self):
        sesion = servicios.abrir(self.usuario, Decimal("100.00"))
        servicios.registrar_movimiento(
            sesion, self.usuario, tipo="ingreso", concepto="Venta", importe=Decimal("50")
        )
        servicios.registrar_movimiento(
            sesion, self.usuario, tipo="egreso", concepto="Cambio", importe=Decimal("20")
        )
        self.assertEqual(sesion.total_ingresos, Decimal("50.00"))
        self.assertEqual(sesion.total_egresos, Decimal("20.00"))
        self.assertEqual(sesion.saldo_esperado, Decimal("130.00"))

        cerrada = servicios.cerrar(sesion, Decimal("120.00"), "Faltó cambio")
        self.assertFalse(cerrada.abierta)
        self.assertEqual(cerrada.saldo_declarado, Decimal("120.00"))
        self.assertEqual(cerrada.diferencia, Decimal("-10.00"))

    def test_no_admite_movimientos_despues_del_cierre(self):
        sesion = servicios.abrir(self.usuario, Decimal("0"))
        servicios.cerrar(sesion, Decimal("0"))
        with self.assertRaises(ValidationError):
            servicios.registrar_movimiento(
                sesion, self.usuario, tipo="ingreso", concepto="Tarde", importe=Decimal("1")
            )

    def test_la_factura_a_credito_no_mueve_la_caja(self):
        sesion = servicios.abrir(self.usuario, Decimal("0"))

        class FacturaFalsa:
            forma_pago = "19"
            total = Decimal("25.00")
            comprobante = None

        servicios.registrar_ingreso_factura(FacturaFalsa(), self.usuario)
        self.assertFalse(MovimientoCaja.objects.filter(sesion=sesion).exists())


class DesgloseYCierreTests(TestCase):
    """El desglose del efectivo y el acta que se firma al cerrar."""

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="cajero-del-turno", password="secreto"
        )
        self.client.force_login(self.usuario)

    def _desglose(self) -> dict:
        return {
            "cantidad_100_00": "1",
            "cantidad_20_00": "2",
            "cantidad_10_00": "1",
            "cantidad_5_00": "1",
            "cantidad_1_00": "3",
            "cantidad_0_50": "2",
            "cantidad_0_25": "3",
            "cantidad_0_10": "4",
            "cantidad_0_01": "7",
            "observaciones_cierre": "Cierre del turno",
        }

    def test_el_total_del_desglose_suma_billetes_y_monedas(self):
        self.assertEqual(
            servicios.total_del_desglose({"100.00": 1, "20.00": 2, "0.25": 3}),
            Decimal("140.75"),
        )
        self.assertEqual(servicios.total_del_desglose({}), Decimal("0"))

    def test_las_denominaciones_van_de_mayor_a_menor(self):
        valores = [str(valor) for valor in servicios.DENOMINACIONES]
        self.assertEqual(valores[0], "100")
        self.assertEqual(valores[-1], "0.01")
        self.assertIn("0.50", valores)
        # Sin repetidas y todas positivas.
        self.assertEqual(len(valores), len(set(valores)))
        self.assertTrue(all(valor > 0 for valor in servicios.DENOMINACIONES))

    def test_el_formulario_del_cierre_calcula_el_efectivo_contado(self):
        from .forms import CerrarCajaForm

        formulario = CerrarCajaForm(self._desglose())

        self.assertTrue(formulario.is_valid(), formulario.errors)
        # 100 + 40 + 10 + 5 + 3 + 1 + 0,75 + 0,40 + 0,07
        self.assertEqual(formulario.cleaned_data["saldo_declarado"], Decimal("160.22"))
        self.assertEqual(formulario.desglose()["100.00"], 1)

    def test_una_caja_vacia_se_cierra_en_cero(self):
        """Todo cobrado con tarjeta deja la caja en 0: se cierra en 0,00 sin pelear."""
        from .forms import CerrarCajaForm

        for datos in ({}, {"cantidad_100_00": "0"}, {"saldo_declarado": "0"}):
            with self.subTest(datos=datos):
                formulario = CerrarCajaForm(datos)
                self.assertTrue(formulario.is_valid(), formulario.errors)
                self.assertEqual(formulario.cleaned_data["saldo_declarado"], Decimal("0.00"))

    def test_la_caja_vacia_se_cierra_y_queda_en_cero(self):
        sesion = servicios.abrir(self.usuario, Decimal("0"))

        self.client.post(
            "/caja/",
            {"accion": "cerrar", "saldo_declarado": "0", "cantidad_100_00": "0"},
            follow=True,
        )

        cerrada = SesionCaja.objects.get(pk=sesion.pk)
        self.assertEqual(cerrada.estado, SesionCaja.Estado.CERRADA.value)
        self.assertEqual(cerrada.saldo_declarado, Decimal("0.00"))

    def test_cerrar_guarda_el_desglose_y_baja_el_acta(self):
        sesion = servicios.abrir(self.usuario, Decimal("160.22"))

        respuesta = self.client.post("/caja/", {**self._desglose(), "accion": "cerrar"}, follow=True)
        self.assertEqual(respuesta.status_code, 200)

        cerrada = SesionCaja.objects.get(pk=sesion.pk)
        self.assertEqual(cerrada.saldo_declarado, Decimal("160.22"))
        self.assertEqual(cerrada.desglose["100.00"], 1)
        self.assertEqual(cerrada.diferencia, Decimal("0.00"))

        acta = self.client.get(f"/caja/acta/{cerrada.pk}/")
        self.assertEqual(acta.status_code, 200)
        self.assertEqual(acta["Content-Type"], "application/pdf")
        self.assertTrue(acta.content.startswith(b"%PDF"))
        self.assertGreater(len(acta.content), 5000)

    def test_el_acta_de_una_caja_abierta_no_se_genera(self):
        sesion = servicios.abrir(self.usuario, Decimal("0"))

        respuesta = self.client.get(f"/caja/acta/{sesion.pk}/")

        self.assertRedirects(respuesta, "/caja/", fetch_redirect_response=False)

    def test_el_acta_de_una_caja_cerrada_por_otro_se_puede_leer(self):
        otro = get_user_model().objects.create_user(username="otro-cajero", password="x")
        sesion = servicios.abrir(otro, Decimal("5.00"))
        servicios.cerrar(sesion, Decimal("5.00"), "Turno corto")

        respuesta = self.client.get(f"/caja/acta/{sesion.pk}/")

        self.assertEqual(respuesta.status_code, 200)
