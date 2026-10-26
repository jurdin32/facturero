"""Pruebas de la tabla de retenciones del SRI.

Lo que se prueba es que la tabla se cargue desde el archivo oficial y que llegue
al comprobante: el código, su impuesto y su porcentaje. Si el SRI publica otra
resolución, se cambia el archivo y estas pruebas siguen diciendo lo mismo.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from comprobantes.forms import RetencionDeSustento

from .models import CodigoRetencion, opciones_de_retencion

__all__ = ["PruebasDeLosCodigosDeRetencion", "PruebasDelBuscadorDeCodigos"]


class PruebasDeLosCodigosDeRetencion(TestCase):
    """La tabla oficial, cargada y a mano del comprobante."""

    @classmethod
    def setUpTestData(cls) -> None:
        call_command("cargar_codigos_retencion", stdout=StringIO())

    def test_se_cargan_los_codigos_del_archivo_del_sri(self) -> None:
        self.assertGreaterEqual(CodigoRetencion.objects.count(), 130)

    def test_un_codigo_de_renta_trae_su_porcentaje(self) -> None:
        honorarios = CodigoRetencion.objects.get(codigo="303")
        self.assertEqual(honorarios.impuesto, "1")
        self.assertEqual(honorarios.porcentaje, Decimal("10"))
        self.assertIn("Honorarios profesionales", honorarios.concepto)

    def test_los_codigos_con_letra_tambien_estan(self) -> None:
        self.assertTrue(CodigoRetencion.objects.filter(codigo="304A").exists())
        self.assertTrue(CodigoRetencion.objects.filter(codigo="312C").exists())

    def test_un_codigo_de_iva_sabe_que_es_de_iva(self) -> None:
        iva = CodigoRetencion.objects.get(codigo="9")
        self.assertEqual(iva.impuesto, "2")
        self.assertEqual(iva.porcentaje, Decimal("10"))

    def test_el_formulario_ofrece_los_codigos_y_su_porcentaje(self) -> None:
        campo = RetencionDeSustento()["codigo_retencion"]
        html = str(campo)

        self.assertIn('value="303"', html)
        self.assertIn('data-porcentaje="10.00"', html)
        self.assertIn('data-impuesto="1"', html)
        self.assertIn('value="9"', html)

    def test_los_codigos_van_agrupados_por_impuesto(self) -> None:
        grupos = dict(opciones_de_retencion())
        self.assertIn("Renta", grupos)
        self.assertIn("IVA", grupos)
        self.assertNotIn("texto libre", grupos)

    def test_volver_a_cargar_no_duplica(self) -> None:
        cuantos = CodigoRetencion.objects.count()
        call_command("cargar_codigos_retencion", stdout=StringIO())
        self.assertEqual(CodigoRetencion.objects.count(), cuantos)


class PruebasDelBuscadorDeCodigos(TestCase):
    """La ventana donde se elige el código: busca y trae lo de la fila."""

    @classmethod
    def setUpTestData(cls) -> None:
        call_command("cargar_codigos_retencion", stdout=StringIO())
        cls.usuario = User.objects.create_user("quien-retiene", password="secreto")

    def setUp(self) -> None:
        self.client.force_login(self.usuario)

    def _buscar(self, texto: str) -> list[dict]:
        respuesta = self.client.get(reverse("comprobantes:buscar_retenciones"), {"q": texto})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()["resultados"]

    def test_busca_por_codigo(self) -> None:
        codigos = [fila["codigo"] for fila in self._buscar("312")]
        self.assertIn("312", codigos)
        self.assertNotIn("303", codigos)

    def test_busca_por_concepto(self) -> None:
        codigos = [fila["codigo"] for fila in self._buscar("honorarios")]
        self.assertIn("303", codigos)

    def test_trae_lo_necesario_para_llenar_la_fila(self) -> None:
        fila = next(fila for fila in self._buscar("9") if fila["codigo"] == "9")
        self.assertEqual(fila["impuesto"], "2")
        self.assertEqual(fila["porcentaje"], "10.00")
        self.assertEqual(fila["como_porcentaje"], "10 %")
        self.assertTrue(fila["etiqueta"].startswith("9 · "))
        self.assertIn("IVA", fila["concepto"])
