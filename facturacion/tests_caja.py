"""Sin caja del turno abierta no se factura.

Es una regla del negocio, no del SRI: cada venta tiene que entrar en el arqueo del
día, y para eso el cajero abre su turno antes de la primera factura. Cuando la caja
se cierra, la pantalla de facturar se vuelve a bloquear hasta el turno siguiente.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from caja.servicios import abrir as abrir_caja
from caja.servicios import cerrar as cerrar_caja

__all__ = ["PruebasDeLaCajaDelTurno"]


class PruebasDeLaCajaDelTurno(TestCase):
    """La facturación depende de la caja abierta."""

    def setUp(self) -> None:
        self.usuario = User.objects.create_user("quien-sin-caja", password="clave-de-pruebas")
        self.client.force_login(self.usuario)

    def test_sin_caja_abierta_no_se_entra_a_facturar(self) -> None:
        respuesta = self.client.get("/facturar/")

        self.assertRedirects(respuesta, "/caja/", fetch_redirect_response=False)
        avisos = [str(aviso) for aviso in respuesta.wsgi_request._messages]
        self.assertTrue(
            any("abrir la caja" in aviso for aviso in avisos), avisos
        )

    def test_con_la_caja_abierta_se_entra_a_facturar(self) -> None:
        abrir_caja(self.usuario)

        self.assertEqual(self.client.get("/facturar/").status_code, 200)

    def test_al_cerrar_la_caja_se_vuelve_a_bloquear(self) -> None:
        sesion = abrir_caja(self.usuario, Decimal("10.00"))

        self.assertEqual(self.client.get("/facturar/").status_code, 200)

        cerrar_caja(sesion, Decimal("10.00"))

        self.assertEqual(self.client.get("/facturar/").status_code, 302)

    def test_el_tablero_avisa_que_falta_abrir_la_caja(self) -> None:
        pagina = self.client.get("/").content.decode()

        self.assertIn("abrir la caja", pagina)

    def test_con_caja_abierta_el_tablero_no_avisa(self) -> None:
        abrir_caja(self.usuario)

        pagina = self.client.get("/").content.decode()

        self.assertNotIn("Todavía no ha abierto su caja", pagina)
