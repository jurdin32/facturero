"""Pruebas del orden del menú por arrastre."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from personalize_options.models import Opcion


class OrdenMenuTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="admin", password="secreto", email="admin@example.com"
        )
        self.client.force_login(self.usuario)
        self.uno = Opcion.objects.create(
            clave="uno", nombre="Uno", grupo="Primero", orden=1, url="/uno/", en_menu=True
        )
        self.dos = Opcion.objects.create(
            clave="dos", nombre="Dos", grupo="Primero", orden=2, url="/dos/", en_menu=True
        )
        self.tres = Opcion.objects.create(
            clave="tres", nombre="Tres", grupo="Segundo", orden=3, url="/tres/", en_menu=True
        )

    def test_la_pantalla_muestra_los_apartados(self):
        respuesta = self.client.get(reverse("seguridad:ordenar_menu"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Primero")
        self.assertContains(respuesta, "Segundo")

    def test_guarda_el_orden_plano(self):
        respuesta = self.client.post(
            reverse("seguridad:guardar_orden_menu"),
            {"opciones": [self.tres.pk, self.uno.pk, self.dos.pk]},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.json()["ok"])
        self.uno.refresh_from_db()
        self.dos.refresh_from_db()
        self.tres.refresh_from_db()
        self.assertEqual(self.tres.orden, 1)
        self.assertEqual(self.uno.orden, 2)
        self.assertEqual(self.dos.orden, 3)

    def test_rechaza_un_orden_vacio(self):
        respuesta = self.client.post(reverse("seguridad:guardar_orden_menu"), {})
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()["ok"])
