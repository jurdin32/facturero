"""Pruebas de la pantalla de facturar.

Lo que se comprueba aquí es el camino que sigue una factura de verdad: se pinta la
hoja, se llena una línea (eligiendo el producto del catálogo) y se guarda. Por eso
el envío se arma leyendo los campos que la propia hoja imprime: si la plantilla
cambia, la prueba lo nota.

Las líneas de más que nadie llenó no pueden estorbar, y lo que no se escribe lo
completa el paquete desde el producto.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from html.parser import HTMLParser
from typing import Any

from django.contrib.auth.models import User
from django.test import TestCase
from factec.django.documentos import Cliente, Factura, Producto
from factec.sri.fechas import hoy_en_ecuador
from inventario.models import Existencia

from caja.servicios import abrir as abrir_caja

__all__ = ["EnvioDeLaHoja", "PruebasDeLaHojaDeFacturar", "PruebasDelGraficoDelTablero"]

#: Lo que un navegador no envía.
SIN_ENVIAR = ("submit", "button", "file", "reset", "image")


class EnvioDeLaHoja(HTMLParser):
    """Los campos de un formulario, tal como los enviaría el navegador."""

    def __init__(self) -> None:
        super().__init__()
        self.datos: dict[str, str] = {}
        self._select: str | None = None
        self._elegida: str | None = None
        self._primera: str | None = None
        self._textarea: str | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        campos = dict(attrs)
        if tag == "input":
            nombre = campos.get("name")
            if nombre and campos.get("type") not in SIN_ENVIAR:
                self.datos[nombre] = campos.get("value", "")
        elif tag == "select":
            self._select = campos.get("name")
            self._elegida = self._primera = None
        elif tag == "option" and self._select:
            valor = campos.get("value", "")
            if self._primera is None:
                self._primera = valor
            if "selected" in campos:
                self._elegida = valor
        elif tag == "textarea":
            nombre = campos.get("name")
            if nombre:
                self._textarea = nombre
                self.datos[nombre] = ""

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self._textarea:
            self.datos[self._textarea] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._select:
            elegida = self._elegida if self._elegida is not None else self._primera
            self.datos[self._select] = elegida or ""
            self._select = None
        elif tag == "textarea":
            self._textarea = None


def _campos(html: str) -> dict[str, str]:
    lector = EnvioDeLaHoja()
    lector.feed(html)
    return lector.datos


class PruebasDeLaHojaDeFacturar(TestCase):
    """La hoja, de punta a punta."""

    def setUp(self) -> None:
        User.objects.create_user("quien-factura", password="x")
        self.client.force_login(User.objects.get(username="quien-factura"))
        # Cada venta entra en el arqueo del turno: sin caja abierta no se factura.
        abrir_caja(User.objects.get(username="quien-factura"))
        self.producto = Producto.objects.create(
            tipo="producto",
            codigo_principal="CAJA-12",
            descripcion="CAJA DE DOCE",
            unidad_medida="CAJA",
            precio_unitario="10.50",
            codigo_porcentaje_iva="4",
            datos_adicionales="MARCA=ACME",
        )
        Existencia.objects.create(producto=self.producto, cantidad=Decimal("100"))
        self.receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA",
            identificacion="1790012345001",
            tipo_identificacion="04",
        )

    # ---------------------------------------------------------------- ayudas

    def _envio(self, *, producto: Producto | None, cantidad: str = "", precio: str = "") -> dict:
        """Arma el envío con lo que pinta la hoja y rellena la primera línea."""
        pagina = self.client.get("/facturar/").content.decode()
        plantilla = re.search(
            r'<template id="plantilla-linea">(.*?)</template>', pagina, re.S
        ).group(1)
        vacia = {
            nombre.replace("detalles-__prefix__-", ""): valor
            for nombre, valor in _campos(plantilla).items()
        }

        envio = {
            nombre: valor
            for nombre, valor in _campos(pagina).items()
            if not nombre.startswith("detalles-")
        }
        envio.update(
            {
                "detalles-TOTAL_FORMS": "3",
                "detalles-INITIAL_FORMS": "0",
                "detalles-MIN_NUM_FORMS": "1",
                "detalles-MAX_NUM_FORMS": "1000",
                "receptor": str(self.receptor.pk),
            }
        )
        for indice in (0, 1, 2):
            for nombre, valor in vacia.items():
                envio[f"detalles-{indice}-{nombre}"] = valor
        if producto is not None:
            envio["detalles-0-producto"] = str(producto.pk)
        if cantidad:
            envio["detalles-0-cantidad"] = cantidad
        if precio:
            envio["detalles-0-precio_unitario"] = precio
        return envio

    # ---------------------------------------------------------------- pruebas

    def test_guardar_el_borrador_completa_la_linea_desde_el_catalogo(self) -> None:
        """Lo que no se escribe lo pone el paquete: el producto ya lo sabe."""
        envio = self._envio(producto=self.producto, cantidad="2")
        envio["accion"] = "guardar"

        respuesta = self.client.post("/facturar/", envio)

        self.assertEqual(respuesta.status_code, 302)
        factura = Factura.objects.get()
        self.assertEqual(respuesta["Location"], f"/facturar/{factura.pk}/")
        linea = factura.detalles.get()
        self.assertEqual(linea.descripcion, "CAJA DE DOCE")
        self.assertEqual(linea.codigo_principal, "CAJA-12")
        self.assertEqual(linea.unidad_medida, "CAJA")
        self.assertEqual(linea.precio_unitario, Decimal("10.5"))
        self.assertEqual(linea.codigo_porcentaje_iva, "4")
        self.assertEqual(linea.datos_adicionales, "MARCA=ACME")
        self.assertEqual(factura.subtotal, Decimal("21"))
        self.assertEqual(factura.total, Decimal("24.15"))

    def test_no_deja_facturar_mas_de_la_existencia(self) -> None:
        """Si se piden 2 y hay 1, no se guarda la factura."""
        Existencia.objects.filter(producto=self.producto).update(cantidad=Decimal("1"))
        envio = self._envio(producto=self.producto, cantidad="2")
        envio["accion"] = "guardar"

        respuesta = self.client.post("/facturar/", envio)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Factura.objects.exists())
        self.assertIn("No hay existencia suficiente", respuesta.content.decode())

    def test_las_lineas_de_mas_no_piden_nada(self) -> None:
        """Dejar dos líneas vacías no puede impedir guardar la factura."""
        envio = self._envio(producto=self.producto)
        envio["accion"] = "guardar"

        respuesta = self.client.post("/facturar/", envio)

        self.assertEqual(respuesta.status_code, 302)
        factura = Factura.objects.get()
        self.assertEqual(factura.detalles.count(), 1)
        self.assertEqual(factura.detalles.get().cantidad, Decimal("1"))

    def test_el_precio_se_escribe_con_coma(self) -> None:
        """En Ecuador el decimal va con coma: 10,50 tiene que entenderse."""
        envio = self._envio(producto=None, precio="10,50")
        envio["detalles-0-descripcion"] = "ALGO SUELTO"
        envio["detalles-0-codigo_porcentaje_iva"] = "4"
        envio["accion"] = "guardar"

        respuesta = self.client.post("/facturar/", envio)

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Factura.objects.get().detalles.get().precio_unitario, Decimal("10.5"))

    def test_la_factura_guardada_se_puede_volver_a_abrir(self) -> None:
        """Editar el borrador tiene que mostrar sus líneas, no una hoja en blanco."""
        self.client.post(
            "/facturar/", {**self._envio(producto=self.producto), "accion": "guardar"}
        )
        factura = Factura.objects.get()

        respuesta = self.client.get(f"/facturar/{factura.pk}/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('value="CAJA DE DOCE"', respuesta.content.decode())

    # -------------------------------------------------- lo que hace la interfaz

    def test_la_factura_no_se_guarda_sin_lineas(self) -> None:
        """La tabla se llena con el buscador: si no hay nada, se avisa en vez de guardar."""
        envio = self._envio(producto=None)
        envio["accion"] = "guardar"

        respuesta = self.client.post("/facturar/", envio)

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(Factura.objects.exists())
        self.assertIn("al menos un producto o servicio", respuesta.content.decode())

    def test_el_buscador_de_productos_encuentra_por_codigo_y_por_descripcion(self) -> None:
        """Lo que el modal necesita para pintar la lista, en una sola llamada."""
        por_nombre = self.client.get("/productos/buscar/", {"q": "caja"}).json()
        por_codigo = self.client.get("/productos/buscar/", {"q": "CAJA-12"}).json()
        sin_nada = self.client.get("/productos/buscar/", {"q": "no existe"}).json()

        self.assertEqual(len(por_nombre["resultados"]), 1)
        self.assertEqual(por_codigo["resultados"][0]["pk"], self.producto.pk)
        self.assertEqual(sin_nada["resultados"], [])

        fila = por_nombre["resultados"][0]
        # La línea se arma con esto sin volver a preguntar por el producto.
        for clave in ("pk", "descripcion", "codigo_principal", "unidad_medida",
                      "precio_unitario", "codigo_porcentaje_iva"):
            self.assertIn(clave, fila)
        self.assertEqual(fila["descripcion"], "CAJA DE DOCE")

    def test_el_buscador_de_clientes_encuentra_por_nombre_y_por_identificacion(self) -> None:
        por_nombre = self.client.get("/clientes/buscar/", {"q": "prueba"}).json()
        por_ruc = self.client.get("/clientes/buscar/", {"q": "1790012345001"}).json()

        self.assertEqual(por_nombre["resultados"][0]["pk"], self.receptor.pk)
        self.assertEqual(por_ruc["resultados"][0]["razon_social"], "CLIENTE DE PRUEBA")
        self.assertEqual(por_nombre["resultados"][0]["identificacion"], "1790012345001")

    def test_la_hoja_avisa_que_se_esta_emitiendo(self) -> None:
        """Al enviar se firma y se espera al SRI: el formulario lo dice para el anillo."""
        pagina = self.client.get("/facturar/").content.decode()

        self.assertIn('data-espera="Firmando y enviando al SRI', pagina)

    def test_la_lista_de_facturas_es_un_listado(self) -> None:
        """La lista la monta Metro, que es la que trae buscador y paginación, y se
        lee como un listado: cada factura con su chip de estado y sin cabecera."""
        receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA", identificacion="1790012345001",
            tipo_identificacion="04",
        )
        Factura.objects.create(receptor=receptor, fecha_emision="2026-10-09")

        pagina = self.client.get("/facturas/").content.decode()

        self.assertIn('id="tabla-facturas"', pagina)
        self.assertIn("data-tabla", pagina)
        self.assertIn("listado", pagina)
        self.assertIn('class="col-marca"', pagina)
        self.assertIn('class="col-principal"', pagina)


class PruebasDelGraficoDelTablero(TestCase):
    """El gráfico de los productos y servicios con más movimiento."""

    def setUp(self) -> None:
        User.objects.create_user("quien-mira-el-tablero", password="clave-de-pruebas")
        self.client.force_login(User.objects.get(username="quien-mira-el-tablero"))
        self.receptor = Cliente.objects.create(
            razon_social="CLIENTE DE PRUEBA",
            identificacion="1790012345001",
            tipo_identificacion="04",
        )
        self.hoy = hoy_en_ecuador()

    def _factura(self, cuando: Any = None, **lineas: Any) -> Factura:
        """Una factura con una línea por cada ``descripcion=(unidades, precio)``."""
        factura = Factura.objects.create(
            receptor=self.receptor, fecha_emision=cuando or self.hoy
        )
        for descripcion, (cantidad, precio) in lineas.items():
            factura.detalles.create(
                descripcion=descripcion, cantidad=cantidad, precio_unitario=precio
            )
        return factura

    def test_el_grafico_ordena_por_unidades_y_da_los_totales(self) -> None:
        self._factura(CAJA=(Decimal("10"), Decimal("1")), HORA=(Decimal("2"), Decimal("10")))

        pagina = self.client.get("/").content.decode()

        self.assertIn("Productos y servicios con más movimiento", pagina)
        self.assertLess(pagina.index("CAJA"), pagina.index("HORA"))
        self.assertIn("12 unidades", pagina)          # 10 de CAJA + 2 de HORA
        self.assertIn("30,00 facturado", pagina)      # 10×1 + 2×10

    def test_se_puede_ordenar_por_importe(self) -> None:
        """El mismo dato, mirado por dinero en vez de por unidades."""
        self._factura(CAJA=(Decimal("10"), Decimal("1")), HORA=(Decimal("2"), Decimal("50")))

        por_unidades = self.client.get("/").content.decode()
        por_importe = self.client.get("/?orden=importe").content.decode()

        self.assertLess(por_unidades.index("CAJA"), por_unidades.index("HORA"))
        self.assertLess(por_importe.index("HORA"), por_importe.index("CAJA"))

    def test_un_orden_desconocido_cae_en_el_de_por_omision(self) -> None:
        self._factura(CAJA=(Decimal("1"), Decimal("1")))

        respuesta = self.client.get("/?orden=lo-que-sea")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("CAJA", respuesta.content.decode())

    def test_el_grafico_solo_mira_el_periodo(self) -> None:
        self._factura(cuando=self.hoy - timedelta(days=40), VIEJO=(Decimal("5"), Decimal("1")))
        self._factura(NUEVO=(Decimal("1"), Decimal("1")))

        pagina = self.client.get("/?dias=14").content.decode()

        self.assertIn("NUEVO", pagina)
        self.assertNotIn("VIEJO", pagina)

    def test_ya_no_estan_los_ultimos_comprobantes(self) -> None:
        self._factura(CAJA=(Decimal("1"), Decimal("1")))

        pagina = self.client.get("/").content.decode()

        self.assertNotIn("Últimos comprobantes", pagina)
        self.assertNotIn("lista-compacta", pagina)
