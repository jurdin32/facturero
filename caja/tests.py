"""Pruebas de la caja por usuario."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase

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


class LasDosCopiasDelActa(TestCase):
    """El acta se imprime entera para quien supervisa y sin saldos para el cajero."""

    def setUp(self) -> None:
        self.cajero = get_user_model().objects.create_user("cajero-acta", password="x")
        self.jefe = get_user_model().objects.create_user("jefe-acta", password="y")
        self.jefe.is_superuser = True
        self.jefe.save()

        self.sesion = servicios.abrir(self.cajero, Decimal("50.00"))
        servicios.registrar_movimiento(
            self.sesion,
            self.cajero,
            tipo="ingreso",
            concepto="cobro",
            importe=Decimal("30.00"),
        )
        servicios.cerrar(self.sesion, Decimal("70.00"), "faltaron diez")
        self.sesion.refresh_from_db()

        self.client = Client(SERVER_NAME="localhost")

    def test_el_cajero_recibe_la_copia_sin_saldos(self) -> None:
        from unittest.mock import patch

        from django.test import override_settings

        from personalize_options.models import Nivel, Permiso, Rol

        # Un cajero de verdad: sólo el permiso de su caja, nada de supervisión.
        rol = Rol.objects.create(nombre="Cajero")
        rol.usuarios.add(self.cajero)
        Permiso.objects.create(rol=rol, opcion="caja", nivel=Nivel.LECTURA.value)

        self.client.force_login(self.cajero)
        with override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True}):
            with patch("caja.views.acta_pdf", return_value=b"%PDF-1.4") as falso:
                respuesta = self.client.get(f"/caja/acta/{self.sesion.pk}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(falso.call_args.kwargs["completo"])

    def test_la_supervision_recibe_el_acta_entera(self) -> None:
        from unittest.mock import patch

        from django.test import override_settings

        self.client.force_login(self.jefe)
        with override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True}):
            with patch("caja.views.acta_pdf", return_value=b"%PDF-1.4") as falso:
                respuesta = self.client.get(f"/caja/acta/{self.sesion.pk}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(falso.call_args.kwargs["completo"])

    def test_la_copia_del_cajero_solo_lleva_el_desglose(self) -> None:
        from unittest.mock import patch

        from .acta import acta

        with patch("caja.acta.papel", return_value=b"%PDF-1.4") as falso:
            acta(self.sesion, self.sesion.movimientos.all(), completo=False)

        contexto = falso.call_args.args[1]
        self.assertFalse(contexto["completo"])
        self.assertEqual(contexto["movimientos"], [])

    def test_la_copia_del_cajero_se_genera_igual(self) -> None:
        from .acta import acta

        contenido = acta(self.sesion, self.sesion.movimientos.all(), completo=False)

        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertGreater(len(contenido), 3000)
