"""Pruebas de la consulta de RUC: primero local, después el SRI."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from factec.django.documentos import Cliente
from sri_consultas import Contribuyente, ResultadoConsulta


class ConsultaIdentificacionTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="facturador", password="secreto"
        )
        self.client.force_login(self.usuario)
        self.url = reverse("catalogos:consultar_identificacion")
        self.identificar = reverse("catalogos:identificar_cliente")

    def test_si_esta_en_la_base_no_consulta_el_sri(self):
        Cliente.objects.create(
            razon_social="CLIENTE GUARDADO",
            identificacion="1790012344001",
            tipo_identificacion="04",
            direccion="QUITO",
        )
        with patch("catalogos.views.consultar_ruc_sri") as consultar:
            respuesta = self.client.get(self.url, {"identificacion": "1790012344001"})
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        self.assertEqual(datos["origen"], "local")
        self.assertEqual(datos["cliente"]["razon_social"], "CLIENTE GUARDADO")
        consultar.assert_not_called()

    def test_si_es_nuevo_lo_completa_con_el_sri(self):
        datos_sri = ResultadoConsulta(
            ruc="1790012345001",
            encontrado=True,
            datos={"Razón social": "CONTRIBUYENTE NUEVO"},
            crudo=Contribuyente.desde_dict(
                {
                    "numeroRuc": "1790012345001",
                    "razonSocial": "CONTRIBUYENTE NUEVO",
                    "estadoContribuyenteRuc": "ACTIVO",
                    "tipoContribuyente": "PERSONA JURÍDICA",
                    "regimen": "RIMPE",
                    "actividadEconomicaPrincipal": "SERVICIOS",
                }
            ),
        )
        with patch("catalogos.views.consultar_ruc_sri", return_value=datos_sri):
            with patch("catalogos.views.direccion_matriz", return_value="GUAYAQUIL"):
                respuesta = self.client.get(self.url, {"identificacion": "1790012345001"})
        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        self.assertEqual(datos["origen"], "sri")
        self.assertEqual(datos["cliente"]["razon_social"], "CONTRIBUYENTE NUEVO")
        self.assertEqual(datos["cliente"]["tipo_identificacion"], "04")
        self.assertEqual(datos["sri"]["tipo_contribuyente"], "PERSONA JURÍDICA")
        self.assertEqual(datos["sri"]["regimen"], "RIMPE")

    def test_una_cedula_nueva_busca_su_ruc_en_el_catastro(self):
        datos_sri = ResultadoConsulta(
            ruc="1712345678001",
            encontrado=True,
            datos={"Razón social": "PERSONA POR CEDULA"},
            crudo=Contribuyente.desde_dict(
                {
                    "numeroRuc": "1712345678001",
                    "razonSocial": "PERSONA POR CEDULA",
                    "estadoContribuyenteRuc": "ACTIVO",
                }
            ),
        )
        with patch("catalogos.views.consultar_ruc_sri", return_value=datos_sri) as consultar:
            with patch("catalogos.views.direccion_matriz", return_value="QUITO / CENTRO"):
                respuesta = self.client.get(self.url, {"identificacion": "1712345678"})
        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        self.assertEqual(datos["cliente"]["identificacion"], "1712345678")
        self.assertEqual(datos["cliente"]["tipo_identificacion"], "05")
        self.assertEqual(datos["cliente"]["direccion"], "QUITO / CENTRO")
        consultar.assert_called_once()
        self.assertEqual(consultar.call_args.args[0], "1712345678001")

    def test_identificar_crea_el_cliente_que_esta_en_el_sri(self):
        datos_sri = ResultadoConsulta(
            ruc="1790012345001",
            encontrado=True,
            datos={"Razón social": "CONTRIBUYENTE NUEVO"},
            crudo=Contribuyente.desde_dict(
                {
                    "numeroRuc": "1790012345001",
                    "razonSocial": "CONTRIBUYENTE NUEVO",
                    "estadoContribuyenteRuc": "ACTIVO",
                    "regimen": "RIMPE",
                }
            ),
        )
        with patch("catalogos.views.consultar_ruc_sri", return_value=datos_sri):
            with patch("catalogos.views.direccion_matriz", return_value="GUAYAQUIL"):
                respuesta = self.client.post(
                    self.identificar, {"identificacion": "1790012345001"}
                )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        cliente = Cliente.objects.get(pk=datos["cliente"]["pk"])
        self.assertEqual(cliente.razon_social, "CONTRIBUYENTE NUEVO")
        self.assertEqual(cliente.tipo_identificacion, "04")
        self.assertEqual(cliente.direccion, "GUAYAQUIL")

    def test_identificar_una_cedula_la_guarda_como_cedula(self):
        datos_sri = ResultadoConsulta(
            ruc="1712345678001",
            encontrado=True,
            crudo=Contribuyente.desde_dict(
                {"numeroRuc": "1712345678001", "razonSocial": "PERSONA POR CEDULA"}
            ),
        )
        with patch("catalogos.views.consultar_ruc_sri", return_value=datos_sri) as consultar:
            with patch("catalogos.views.direccion_matriz", return_value="QUITO"):
                respuesta = self.client.post(
                    self.identificar, {"identificacion": "1712345678"}
                )

        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        cliente = Cliente.objects.get(pk=datos["cliente"]["pk"])
        self.assertEqual(cliente.identificacion, "1712345678")
        self.assertEqual(cliente.tipo_identificacion, "05")
        self.assertEqual(consultar.call_args.args[0], "1712345678001")

    def test_el_ruc_y_la_cedula_pueden_convivir(self):
        cedula = Cliente.objects.create(
            razon_social="PERSONA CON CEDULA",
            identificacion="1712345678",
            tipo_identificacion="05",
        )
        datos_sri = ResultadoConsulta(
            ruc="1712345678001",
            encontrado=True,
            crudo=Contribuyente.desde_dict(
                {
                    "numeroRuc": "1712345678001",
                    "razonSocial": "PERSONA CON CEDULA",
                    "estadoContribuyenteRuc": "ACTIVO",
                }
            ),
        )
        with patch("catalogos.views.consultar_ruc_sri", return_value=datos_sri):
            with patch("catalogos.views.direccion_matriz", return_value="QUITO"):
                respuesta = self.client.post(
                    self.identificar, {"identificacion": "1712345678001"}
                )

        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        self.assertNotEqual(datos["cliente"]["pk"], cedula.pk)
        self.assertEqual(Cliente.objects.filter(identificacion="1712345678").count(), 1)
        self.assertEqual(Cliente.objects.filter(identificacion="1712345678001").count(), 1)

    def test_un_pasaporte_se_busca_por_su_tipo(self):
        pasaporte = Cliente.objects.create(
            razon_social="PERSONA CON PASAPORTE",
            identificacion="AB12345678",
            tipo_identificacion="06",
        )

        respuesta = self.client.post(
            self.identificar,
            {"identificacion": "AB12345678", "tipo_identificacion": "06"},
        )

        datos = respuesta.json()
        self.assertTrue(datos["encontrado"])
        self.assertEqual(datos["cliente"]["pk"], pasaporte.pk)
        self.assertEqual(datos["cliente"]["tipo_identificacion"], "06")
        self.assertEqual(datos["cliente"]["identificacion"], "AB12345678")

    def test_un_pasaporte_nuevo_no_consulta_el_sri(self):
        with patch("catalogos.views.consultar_ruc_sri") as consultar:
            respuesta = self.client.post(
                self.identificar,
                {"identificacion": "XY987654", "tipo_identificacion": "06"},
            )

        datos = respuesta.json()
        self.assertFalse(datos["encontrado"])
        self.assertTrue(datos["pedir_datos"])
        consultar.assert_not_called()

    def test_si_no_esta_en_el_sri_pide_los_datos(self):
        with patch(
            "catalogos.views.consultar_ruc_sri",
            return_value=ResultadoConsulta(ruc="1790012345001", encontrado=False),
        ):
            respuesta = self.client.post(
                self.identificar, {"identificacion": "1790012345001"}
            )

        datos = respuesta.json()
        self.assertFalse(datos["encontrado"])
        self.assertTrue(datos["pedir_datos"])
        self.assertFalse(Cliente.objects.filter(identificacion="1790012345001").exists())
