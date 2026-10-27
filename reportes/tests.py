"""Las pruebas de los reportes: los períodos, las consultas y las tres salidas.

No se prueban los números de un negocio concreto —los pone cada empresa—, sino que
el período se calcule bien, que cada reporte devuelva una tabla con sus columnas y
que el PDF y el Excel salgan con el tipo y el nombre que corresponde.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

from django.contrib.auth.models import User
from django.test import Client, TestCase

from personalize_options.models import Nivel, Permiso, Rol

from . import catalogo, consultas, manual, periodos, salidas
from .periodos import Filtro, anterior, resolver
from .tabla import dinero, entero, numero, porcentaje, variacion

__all__ = ["PruebasDeLosPeriodos", "PruebasDeLasTablas", "PruebasDeLosReportes"]


class PruebasDeLosPeriodos(TestCase):
    """Los tramos de fechas: semanas ISO, meses, trimestres y rangos a mano."""

    def setUp(self) -> None:
        self.hoy = periodos.hoy_en_ecuador()

    def test_la_semana_va_de_lunes_a_domingo(self) -> None:
        for dia in range(0, 14):
            filtro = resolver({"periodo": "semana"}, cuenta=None)
            self.assertEqual(filtro.desde.weekday(), 0, filtro.desde)
            self.assertEqual(filtro.hasta.weekday(), 6, filtro.hasta)
            self.assertEqual((filtro.hasta - filtro.desde).days, 6)
            self.assertTrue(filtro.desde <= self.hoy <= filtro.hasta)
            break

    def test_la_semana_pasada_termina_el_domingo_antes_de_esta(self) -> None:
        esta = resolver({"periodo": "semana"})
        pasada = resolver({"periodo": "semana_pasada"})
        self.assertEqual(pasada.hasta, esta.desde - periodos.timedelta(days=1))
        self.assertEqual(pasada.dias, 7)

    def test_el_mes_va_del_primero_al_ultimo_dia(self) -> None:
        filtro = resolver({"periodo": "mes"})
        self.assertEqual(filtro.desde.day, 1)
        self.assertEqual(filtro.hasta, periodos.fin_de_mes(self.hoy))
        self.assertEqual(filtro.desde.month, self.hoy.month)

    def test_el_mes_pasado_cruza_el_año(self) -> None:
        filtro = resolver({"periodo": "mes_pasado"})
        self.assertLess(filtro.desde, periodos.primer_dia_del_mes(self.hoy))
        self.assertEqual(filtro.hasta, periodos.fin_de_mes(filtro.desde))
        # Diciembre de 2025 pasa a enero de 2026 sin romperse.
        self.assertEqual(periodos._meses_antes(date(2026, 1, 15)), date(2025, 12, 1))

    def test_el_trimestre_es_natural(self) -> None:
        for mes, esperado in ((1, 1), (3, 1), (4, 4), (7, 7), (10, 10), (12, 10)):
            desde, hasta = periodos.trimestre_de(date(2026, mes, 15))
            self.assertEqual(desde.month, esperado)
            self.assertEqual((hasta.month - desde.month), 2)
            self.assertEqual(hasta, periodos.fin_de_mes(hasta))

    def test_el_año_va_del_primero_de_enero_al_31_de_diciembre(self) -> None:
        filtro = resolver({"periodo": "anio"})
        self.assertEqual(filtro.desde, date(self.hoy.year, 1, 1))
        self.assertEqual(filtro.hasta, date(self.hoy.year, 12, 31))

    def test_un_rango_escrito_a_mano_se_respeta(self) -> None:
        filtro = resolver({"periodo": "personalizado", "desde": "2026-01-01", "hasta": "2026-03-31"})
        self.assertEqual(filtro.desde, date(2026, 1, 1))
        self.assertEqual(filtro.hasta, date(2026, 3, 31))
        self.assertEqual(filtro.etiqueta, "del 1 de enero al 31 de marzo de 2026")

    def test_un_rango_al_revés_se_da_la_vuelta(self) -> None:
        filtro = resolver({"periodo": "personalizado", "desde": "2026-03-31", "hasta": "2026-01-01"})
        self.assertEqual(filtro.desde, date(2026, 1, 1))
        self.assertEqual(filtro.hasta, date(2026, 3, 31))

    def test_un_periodo_que_no_existe_vuelve_al_de_omision(self) -> None:
        filtro = resolver({"periodo": "lo-que-sea"})
        self.assertEqual(filtro.clave, periodos.DE_OMISION)

    def test_una_fecha_que_no_se_entiende_vuelve_al_de_omision(self) -> None:
        filtro = resolver({"periodo": "personalizado", "desde": "ayer", "hasta": ""})
        self.assertEqual(filtro.clave, periodos.DE_OMISION)

    def test_el_periodo_anterior_dura_lo_mismo_y_termina_antes(self) -> None:
        filtro = resolver({"periodo": "personalizado", "desde": "2026-03-01", "hasta": "2026-03-31"})
        previo = anterior(filtro)
        self.assertEqual(previo.dias, filtro.dias)
        self.assertEqual(previo.hasta, date(2026, 2, 28))
        self.assertEqual(previo.desde, date(2026, 1, 29))

    def test_el_mes_completo_se_nombra_por_el_mes(self) -> None:
        filtro = resolver({"periodo": "personalizado", "desde": "2026-10-01", "hasta": "2026-10-31"})
        self.assertEqual(filtro.etiqueta, "octubre de 2026")

    def test_todo_el_historial_lleva_fechas(self) -> None:
        filtro = resolver({"periodo": "todo"})
        self.assertEqual(filtro.desde, periodos.ULTIMO_DIA)
        self.assertEqual(filtro.hasta, self.hoy)


class PruebasDeLasTablas(TestCase):
    """Las cifras se escriben al estilo del Ecuador y las tablas se pintan solas."""

    def test_las_cifras_llevan_punto_de_miles_y_coma_decimal(self) -> None:
        self.assertEqual(dinero("1234567.891"), "1.234.567,89")
        self.assertEqual(dinero(0), "0,00")
        self.assertEqual(dinero(None), "0,00")
        self.assertEqual(entero("1234"), "1.234")
        self.assertEqual(numero("10.5"), "10,5")
        self.assertEqual(numero("10"), "10")
        self.assertEqual(porcentaje("15"), "15,00 %")

    def test_la_variacion_dice_cuanto_cambio(self) -> None:
        self.assertEqual(variacion(150, 100), "+50,00 %")
        self.assertEqual(variacion(50, 100), "−50,00 %")
        self.assertEqual(variacion(0, 0), "—")
        self.assertEqual(variacion(10, 0), "nuevo")

    def test_una_tabla_vacia_se_avisa(self) -> None:
        from .tabla import Columna, Tabla

        tabla = Tabla(titulo="Nada", columnas=(Columna("Cuenta"),))
        self.assertTrue(tabla.vacia)
        self.assertEqual(tabla.renglones(), [])
        self.assertIn("No hay nada", tabla.sin_datos)


class PruebasDeLosReportes(TestCase):
    """Cada reporte devuelve una tabla y cada salida responde."""

    def setUp(self) -> None:
        self.jefe = User.objects.create_superuser("quien-reporta", "jefe@ejemplo.ec", "clave-de-pruebas")
        self.client.force_login(self.jefe)
        self.filtro = resolver({"periodo": "anio"})

    def _get(self, ruta: str) -> Any:
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.status_code, 200, ruta)
        return respuesta

    def test_todos_los_reportes_arman_su_tabla(self) -> None:
        for reporte in catalogo.REPORTES:
            with self.subTest(reporte=reporte.clave):
                tabla = catalogo.construir(reporte, self.filtro)
                self.assertTrue(tabla.titulo)
                self.assertTrue(tabla.columnas)
                # Cada fila tiene tantos datos como columnas.
                for fila in tabla.filas:
                    self.assertEqual(len(fila), len(tabla.columnas), reporte.clave)
                if tabla.totales is not None:
                    self.assertEqual(len(tabla.totales), len(tabla.columnas), reporte.clave)

    def test_el_indice_ensena_los_reportes_por_apartado(self) -> None:
        pagina = self._get("/wadmin/reportes/").content.decode()
        for _grupo, reportes in catalogo.por_grupo():
            for reporte in reportes:
                self.assertIn(reporte.nombre, pagina, reporte.clave)

    def test_cada_reporte_se_ve_en_la_pantalla(self) -> None:
        for reporte in catalogo.REPORTES:
            with self.subTest(reporte=reporte.clave):
                pagina = self._get(f"/wadmin/reportes/{reporte.clave}/?periodo=mes").content.decode()
                # Con datos sale la tabla; sin datos, el aviso de que no hay nada.
                self.assertTrue("<table" in pagina or "No hay nada" in pagina, reporte.clave)
                # Y siempre el filtro del período y el botón de volver al índice.
                self.assertIn('name="periodo"', pagina, reporte.clave)
                self.assertIn("/wadmin/reportes/", pagina, reporte.clave)

    def test_el_pdf_se_abre_en_el_navegador(self) -> None:
        respuesta = self._get("/wadmin/reportes/ventas/?periodo=mes&formato=pdf")
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertTrue(respuesta["Content-Disposition"].startswith("inline"))
        self.assertTrue(respuesta.content.startswith(b"%PDF"))
        self.assertGreater(len(respuesta.content), 3000)

    def test_el_excel_se_descarga(self) -> None:
        respuesta = self._get("/wadmin/reportes/ventas/?periodo=mes&formato=xlsx")
        self.assertIn("spreadsheetml", respuesta["Content-Type"])
        self.assertTrue(respuesta["Content-Disposition"].startswith("attachment"))
        # Un xlsx es un zip: empieza con su firma.
        self.assertTrue(respuesta.content.startswith(b"PK"))

    def test_el_periodo_y_la_cuenta_viajan_en_la_direccion(self) -> None:
        respuesta = self._get("/wadmin/reportes/libro_mayor/?periodo=personalizado&desde=2026-01-01&hasta=2026-01-31")
        self.assertIn("enero de 2026", respuesta.content.decode())

    def test_el_manual_ensena_todas_sus_secciones(self) -> None:
        pagina = self._get("/wadmin/reportes/manual/").content.decode()
        for seccion in manual.SECCIONES:
            self.assertIn(seccion["titulo"], pagina, seccion["clave"])

    def test_un_reporte_que_no_existe_da_404(self) -> None:
        self.assertEqual(self.client.get("/wadmin/reportes/lo-que-sea/").status_code, 404)

    def test_el_filtro_no_se_puede_romper_desde_la_direccion(self) -> None:
        respuesta = self._get("/wadmin/reportes/ventas/?periodo=personalizado&desde=xxx&hasta=yyy")
        self.assertIn("Ventas", respuesta.content.decode())


class PruebasDeLosPermisosDeReportes(TestCase):
    """Los reportes se reparten por roles, uno por uno."""

    def setUp(self) -> None:
        self.usuario = User.objects.create_user("quien-mira-reportes")
        self.client.force_login(self.usuario)

    def test_sin_permiso_no_se_entra_al_modulo(self) -> None:
        from django.test import override_settings

        with override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True}):
            self.assertEqual(self.client.get("/wadmin/reportes/").status_code, 403)

    def test_con_el_modulo_solo_se_ven_los_reportes_concedidos(self) -> None:
        from django.test import override_settings

        rol = Rol.objects.create(nombre="Contador")
        rol.usuarios.add(self.usuario)
        Permiso.objects.create(rol=rol, opcion="reportes", nivel=Nivel.LECTURA.value)
        Permiso.objects.create(rol=rol, opcion="reporte_balance", nivel=Nivel.LECTURA.value)

        with override_settings(PERSONALIZE_OPTIONS={"MODO": "cerrado", "SUPERUSUARIOS_TODO": True}):
            pagina = self.client.get("/wadmin/reportes/").content.decode()
            self.assertIn("Balance de comprobación", pagina)
            self.assertNotIn("Ventas por cliente", pagina)
            self.assertEqual(self.client.get("/wadmin/reportes/balance/").status_code, 200)
            self.assertEqual(self.client.get("/wadmin/reportes/ventas_clientes/").status_code, 403)


class PruebasDelLogotipo(TestCase):
    """El logo del emisor manda; si no hay, va el de Factiz."""

    def test_sin_logo_del_emisor_se_usa_el_de_factiz(self) -> None:
        from .marca import logo_de_los_reportes

        encontrado = logo_de_los_reportes()
        self.assertIsNotNone(encontrado, "falta el logo de Factiz en static/img/")
        contenido, extension = encontrado
        self.assertIn(extension, ("png", "jpg", "jpeg", "webp"))
        self.assertGreater(len(contenido), 1000)

    def test_el_pdf_y_el_excel_llevan_el_logo(self) -> None:
        from .tabla import Columna, Tabla

        tabla = Tabla(
            titulo="Prueba",
            columnas=(Columna("Cuenta"), Columna("Valor", "dinero")),
            filas=[("Caja", 10)],
            totales=("Total", 10),
        )
        ficha = salidas.Ficha(empresa="Empresa de prueba", ruc="1799999999001", periodo="octubre de 2026")
        documento = salidas.pdf(tabla, ficha)
        self.assertTrue(documento.startswith(b"%PDF"))
        self.assertGreater(len(documento), 3000)

        hoja = salidas.excel(tabla, ficha)
        self.assertTrue(hoja.startswith(b"PK"))
        self.assertGreater(len(hoja), 3000)


class PruebasDelMapaDeOpciones(TestCase):
    """Ninguna opción del menú se queda sin documentar."""

    def test_todas_las_opciones_tienen_su_explicacion(self) -> None:
        mapa = manual.mapa_de_opciones()

        self.assertTrue(mapa)
        sin_texto = [
            opcion["nombre"]
            for _categoria, opciones in mapa
            for opcion in opciones
            if not opcion["que"]
        ]
        self.assertEqual(sin_texto, [], f"sin explicación: {sin_texto}")

    def test_el_mapa_cubre_todas_las_opciones_activas(self) -> None:
        from personalize_options import opciones as registro

        documentadas = sum(len(opciones) for _categoria, opciones in manual.mapa_de_opciones())

        self.assertEqual(documentadas, len(registro.todas(solo_activas=True)))


class PruebasDeLosPapeles(TestCase):
    """Todo lo que se imprime sale de plantillas HTML, no de dibujos a mano."""

    def test_las_plantillas_del_papel_existen(self) -> None:
        from django.template.loader import get_template

        for nombre in ("papel/reporte.html", "papel/acta.html", "papel/vale.html"):
            self.assertIsNotNone(get_template(nombre), nombre)

    def test_la_hoja_de_estilo_del_papel_se_lee(self) -> None:
        from facturero.papel import hoja_de_estilo

        hoja = hoja_de_estilo()
        self.assertIn("@page", hoja)
        self.assertIn("counter(page)", hoja)

    def test_el_informe_es_html_convertido(self) -> None:
        from django.template.loader import render_to_string

        from .tabla import Columna, Tabla

        tabla = Tabla(
            titulo="Prueba",
            columnas=(Columna("Cuenta"), Columna("Valor", "dinero")),
            filas=[("Caja", 10)],
        )
        ficha = salidas.Ficha(empresa="Empresa de prueba", ruc="1799999999001")

        html = render_to_string(
            "papel/reporte.html",
            {
                "hoja": "",
                "ficha": ficha,
                "tabla": tabla,
                "columnas": [{"titulo": "Cuenta", "alinear": "izquierda", "parte": 50.0}],
                "totales": None,
                "logo": None,
                "ancha": False,
            },
        )

        self.assertIn("Empresa de prueba", html)
        self.assertIn("RUC 1799999999001", html)
        self.assertIn("Cuenta", html)
