"""Pruebas de los colores de los estados y de las barras de progreso.

Los estados se pintan en toda la aplicación y tienen que salir siempre con el
mismo color, vengan como vengan: el valor interno («AUTORIZADO»), su etiqueta
(«Autorizado») o las palabras de un movimiento del inventario («entrada»).
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase
from factec.django.models import EstadoComprobante

from . import chips


class PruebasDeLosChips(SimpleTestCase):
    def test_cada_estado_tiene_su_color(self) -> None:
        self.assertEqual(chips.chip(EstadoComprobante.AUTORIZADO), "success soft")
        self.assertEqual(chips.chip(EstadoComprobante.DEVUELTO), "alert soft")
        self.assertEqual(chips.chip(EstadoComprobante.FIRMADO), "warning soft")
        self.assertEqual(chips.chip(EstadoComprobante.EN_PROCESO), "info soft")

    def test_tambien_entiende_las_etiquetas(self) -> None:
        """Las plantillas pasan unas veces el valor y otras la etiqueta."""
        self.assertEqual(chips.chip("Autorizado"), "success soft")
        self.assertEqual(chips.chip("Recibido por el SRI"), "info soft")
        self.assertEqual(chips.chip("Devuelto por el SRI"), "alert soft")

    def test_los_movimientos_del_inventario(self) -> None:
        self.assertEqual(chips.chip("entrada"), "success soft")
        self.assertEqual(chips.chip("salida"), "alert soft")
        self.assertEqual(chips.chip("ajuste"), "warning soft")

    def test_lo_que_no_conoce_no_se_pinta_de_ningun_color(self) -> None:
        self.assertEqual(chips.chip("inventado"), "")
        self.assertEqual(chips.chip(""), "")

    def test_el_borrador_va_sin_color(self) -> None:
        self.assertEqual(chips.chip(EstadoComprobante.BORRADOR), "")

    def test_quien_esta_en_manos_del_sri(self) -> None:
        self.assertTrue(chips.en_marcha(EstadoComprobante.RECIBIDO))
        self.assertTrue(chips.en_marcha("En proceso de autorización"))
        self.assertFalse(chips.en_marcha(EstadoComprobante.AUTORIZADO))
        self.assertFalse(chips.en_marcha(EstadoComprobante.BORRADOR))

    def test_el_avance_del_ciclo(self) -> None:
        self.assertEqual(chips.avance(EstadoComprobante.AUTORIZADO), 100)
        self.assertEqual(chips.avance(EstadoComprobante.BORRADOR), 10)
        self.assertEqual(chips.avance("SIN EMITIR"), 0)
        self.assertEqual(chips.avance("lo que sea"), 0)

    def test_de_que_color_va_la_barra_del_ciclo(self) -> None:
        self.assertEqual(chips.clase_avance(EstadoComprobante.AUTORIZADO), "exito")
        self.assertEqual(chips.clase_avance(EstadoComprobante.DEVUELTO), "peligro")
        self.assertEqual(chips.clase_avance(EstadoComprobante.RECIBIDO), "cuidado")
        self.assertEqual(chips.clase_avance(EstadoComprobante.BORRADOR), "")
        self.assertEqual(chips.clase_avance(""), "")

    def test_el_nombre_largo_del_estado(self) -> None:
        self.assertEqual(chips.nombre(EstadoComprobante.AUTORIZADO), "Autorizado")
        self.assertEqual(chips.nombre("Autorizado"), "Autorizado")
        self.assertEqual(chips.nombre("entrada"), "Entrada")


class PruebasDeLaCobertura(SimpleTestCase):
    """La barra de existencias de un bien: 100 % es el doble del mínimo."""

    def cobertura(self, cantidad: str, minimo: str) -> tuple[int, str]:
        from inventario.models import Existencia

        existencia = Existencia(cantidad=Decimal(cantidad), minimo=Decimal(minimo))
        return existencia.cobertura, existencia.clase_cobertura

    def test_la_barra_va_de_cero_a_cien(self) -> None:
        self.assertEqual(self.cobertura("0", "10"), (0, "peligro"))
        self.assertEqual(self.cobertura("5", "10"), (25, "cuidado"))
        self.assertEqual(self.cobertura("10", "10"), (50, "cuidado"))
        self.assertEqual(self.cobertura("20", "10"), (100, "exito"))
        self.assertEqual(self.cobertura("40", "10"), (100, "exito"))

    def test_sin_minimo_no_hay_barra(self) -> None:
        self.assertEqual(self.cobertura("7", "0"), (0, "exito"))
