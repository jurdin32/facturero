"""Pruebas de la trazabilidad de usuario por comprobante."""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from . import auditoria
from .models import RegistroComprobante


class AuditoriaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="vendedor", password="secreto", first_name="Vendedor"
        )

    def test_registra_y_actualiza_el_usuario(self):
        objeto = SimpleNamespace(pk=7, TIPO_COMPROBANTE="01", comprobante=None, secuencial="")
        auditoria.registrar(objeto, self.usuario)
        registro = RegistroComprobante.objects.get(tipo="01", objeto_id=7)
        self.assertEqual(registro.usuario, self.usuario)
        self.assertIn("Vendedor", registro.usuario_nombre)
        self.assertEqual(auditoria.de(objeto).pk, registro.pk)

        otro = get_user_model().objects.create_user(username="otro", password="secreto")
        auditoria.registrar(objeto, otro)
        self.assertEqual(RegistroComprobante.objects.filter(tipo="01", objeto_id=7).count(), 1)
        self.assertEqual(auditoria.de(objeto).usuario, otro)
