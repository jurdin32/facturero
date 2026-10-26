"""Pruebas del asistente de configuración del SRI.

Se prueba lo que promete la pantalla: que cada paso guarde lo suyo, que el
certificado no se dé por bueno sin abrirlo antes, que los secuenciales se creen
al vuelo y que el paso de comprobar enseñe lo que dice el paquete.

La consulta al catastro del SRI se sustituye por una respuesta de mentira: salir
a la red en una prueba es pedir que falle el día que no haya internet.
"""

from __future__ import annotations

import functools
import shutil
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from factec.django import sri_datos
from factec.django.models import ConfiguracionEmisor, Secuencial, TipoComprobante
from factec.excepciones import ErrorFacturacion
from factec.sri.consulta_ruc import DatosRuc

#: Las pruebas guardan el certificado en un directorio temporal, no en media/.
MEDIA_DE_PRUEBA = tempfile.mkdtemp(prefix="facturero-configuracion-")

RUC = "0703886697001"
RAZON_SOCIAL = "URDIN GONZALEZ JOHNNY EDGAR"
CLAVE = "clave-de-prueba"


def tearDownModule() -> None:
    shutil.rmtree(MEDIA_DE_PRUEBA, ignore_errors=True)


@functools.lru_cache(maxsize=None)
def certificado_de_prueba(clave: str = CLAVE, ruc: str = RUC) -> bytes:
    """Un ``.p12`` autofirmado de verdad, con el RUC en el serialNumber.

    El paquete exige que la clave sea RSA (el SRI no admite otras), así que se
    genera una. Se guarda en memoria del módulo: generarla cuesta un segundo y
    todas las pruebas usan la misma.
    """
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeto = x509.Name(
        [
            x509.NameAttribute(NameOID.SERIAL_NUMBER, ruc),
            x509.NameAttribute(NameOID.COMMON_NAME, RAZON_SOCIAL),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"),
        ]
    )
    ahora = datetime.now(dt_timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(sujeto)
        .issuer_name(sujeto)
        .public_key(llave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(days=1))
        .not_valid_after(ahora + timedelta(days=365))
        .sign(llave, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"prueba",
        key=llave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(clave.encode("utf-8")),
    )


def resultado_del_sri(razon_social: str = RAZON_SOCIAL) -> sri_datos.ResultadoConsulta:
    """Lo que devolvería el catastro del SRI al preguntar por un RUC."""
    datos = DatosRuc(
        ruc=RUC,
        razon_social=razon_social,
        estado="ACTIVO",
        regimen="RIMPE",
        categoria="NEGOCIO POPULAR",
        obligado_contabilidad=False,
        encontrado=True,
    )
    return sri_datos.ResultadoConsulta(
        datos=datos, campos=sri_datos.mapear_datos(datos), avisos=[]
    )


@override_settings(MEDIA_ROOT=MEDIA_DE_PRUEBA)
class AsistenteTests(TestCase):
    """El asistente con una configuración ya puesta."""

    def setUp(self) -> None:
        usuario = get_user_model().objects.create_user("prueba", password="clave")
        self.client.force_login(usuario)
        self.configuracion = ConfiguracionEmisor.objects.create(
            nombre="Principal",
            ambiente=1,
            ruc=RUC,
            razon_social=RAZON_SOCIAL,
            nombre_comercial="DIZOF",
            dir_matriz="PANAMERICANA Y CARCHI",
            estab="001",
            pto_emi="001",
        )

    def url(self, paso: int) -> str:
        return f"{reverse('configuracion:sri')}?paso={paso}&c={self.configuracion.pk}"

    # ---------------------------------------------------------------- los pasos

    def test_cada_paso_se_pinta_con_lo_suyo(self):
        esperado = {
            1: "El contribuyente",
            2: "Por dónde va la numeración",
            3: "El archivo y su contraseña",
            4: "Lo que dice el paquete",
        }
        for paso, texto in esperado.items():
            respuesta = self.client.get(self.url(paso))
            self.assertEqual(respuesta.status_code, 200, f"paso {paso}")
            self.assertContains(respuesta, "Configuración del SRI")
            self.assertContains(respuesta, texto)

    def test_el_paso_uno_guarda_los_datos_del_emisor(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                "paso": "1",
                "c": str(self.configuracion.pk),
                "ruc": RUC,
                "razon_social": "ACME S.A.",
                "nombre_comercial": "ACME",
                "dir_matriz": "Av. Siempre Viva 742",
                "dir_establecimiento": "",
                "regimen": "GENERAL",
                "categoria": "",
                "contribuyente_especial": "",
                "agente_retencion": "",
                "campos_adicionales": "VENDEDOR=JOHNNY",
            },
        )
        self.assertRedirects(respuesta, self.url(2))
        self.configuracion.refresh_from_db()
        self.assertEqual(self.configuracion.razon_social, "ACME S.A.")
        self.assertEqual(self.configuracion.campos_adicionales, "VENDEDOR=JOHNNY")

    def test_el_paso_uno_trae_los_datos_del_sri(self):
        with patch(
            "configuracion.forms.sri_datos.consultar_datos",
            return_value=resultado_del_sri(),
        ):
            respuesta = self.client.post(
                reverse("configuracion:sri"),
                {
                    "paso": "1",
                    "c": str(self.configuracion.pk),
                    "consultar_sri": "on",
                    "ruc": RUC,
                    "razon_social": "",
                    "nombre_comercial": "",
                    "dir_matriz": "PANAMERICANA Y CARCHI",
                    "dir_establecimiento": "",
                    "regimen": "",
                    "categoria": "",
                    "contribuyente_especial": "",
                    "agente_retencion": "",
                    "campos_adicionales": "",
                },
            )
        self.assertRedirects(respuesta, self.url(2))
        self.configuracion.refresh_from_db()
        self.assertEqual(self.configuracion.razon_social, RAZON_SOCIAL)
        self.assertEqual(self.configuracion.regimen, "RIMPE")
        self.assertEqual(self.configuracion.categoria, "NEGOCIO POPULAR")

    def test_si_el_sri_no_contesta_avisa_en_el_ruc(self):
        with patch(
            "configuracion.forms.sri_datos.consultar_datos",
            side_effect=ErrorFacturacion("sin respuesta"),
        ):
            respuesta = self.client.post(
                reverse("configuracion:sri"),
                {
                    "paso": "1",
                    "c": str(self.configuracion.pk),
                    "consultar_sri": "on",
                    "ruc": RUC,
                    "razon_social": RAZON_SOCIAL,
                    "dir_matriz": "PANAMERICANA Y CARCHI",
                    "nombre_comercial": "",
                    "dir_establecimiento": "",
                    "regimen": "RIMPE",
                    "categoria": "",
                    "contribuyente_especial": "",
                    "agente_retencion": "",
                    "campos_adicionales": "",
                },
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo consultar el RUC en el SRI")

    def test_el_ruc_tiene_que_tener_trece_digitos(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                "paso": "1",
                "c": str(self.configuracion.pk),
                "ruc": "123",
                "razon_social": RAZON_SOCIAL,
                "dir_matriz": "PANAMERICANA Y CARCHI",
                "nombre_comercial": "",
                "dir_establecimiento": "",
                "regimen": "",
                "categoria": "",
                "contribuyente_especial": "",
                "agente_retencion": "",
                "campos_adicionales": "",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El RUC debe tener 13 dígitos")
        self.configuracion.refresh_from_db()
        self.assertEqual(self.configuracion.ruc, RUC)

    # ------------------------------------------------------- ambiente y serie

    def test_el_paso_dos_guarda_ambiente_y_serie(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                "paso": "2",
                "c": str(self.configuracion.pk),
                "nombre": "Producción",
                "ambiente": "2",
                "estab": "002",
                "pto_emi": "003",
                "activo": "on",
            },
        )
        self.assertRedirects(respuesta, self.url(2))
        self.configuracion.refresh_from_db()
        self.assertEqual(self.configuracion.ambiente, 2)
        self.assertEqual((self.configuracion.estab, self.configuracion.pto_emi), ("002", "003"))

    def test_la_serie_tiene_que_ser_de_tres_digitos(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                "paso": "2",
                "c": str(self.configuracion.pk),
                "nombre": "Principal",
                "ambiente": "1",
                "estab": "1",
                "pto_emi": "001",
                "activo": "on",
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "3 dígitos")
        self.configuracion.refresh_from_db()
        self.assertEqual(self.configuracion.estab, "001")

    def _datos_del_formset(self, **ultimos: int) -> dict:
        """El POST de la tabla de secuenciales, con los seis tipos."""
        datos = {
            "secuencial-TOTAL_FORMS": str(len(TipoComprobante.choices)),
            "secuencial-INITIAL_FORMS": str(len(TipoComprobante.choices)),
            "secuencial-MIN_NUM_FORMS": "0",
            "secuencial-MAX_NUM_FORMS": "1000",
        }
        for indice, (tipo, _) in enumerate(TipoComprobante.choices):
            datos[f"secuencial-{indice}-tipo_comprobante"] = tipo
            datos[f"secuencial-{indice}-estab"] = "001"
            datos[f"secuencial-{indice}-pto_emi"] = "001"
            datos[f"secuencial-{indice}-ambiente"] = "1"
            datos[f"secuencial-{indice}-ultimo"] = str(ultimos.get(tipo, 0))
        return datos

    def test_los_secuenciales_se_crean_y_se_actualizan(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                **self._datos_del_formset(**{"01": 41}),
                "paso": "2",
                "que": "secuenciales",
                "c": str(self.configuracion.pk),
            },
        )
        self.assertRedirects(respuesta, self.url(2))
        self.assertEqual(Secuencial.objects.count(), len(TipoComprobante.choices))
        self.assertEqual(
            Secuencial.objects.get(tipo_comprobante="01", ambiente=1).ultimo, 41
        )

    def test_un_secuencial_negativo_no_cuela(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                **self._datos_del_formset(**{"01": -1}),
                "paso": "2",
                "que": "secuenciales",
                "c": str(self.configuracion.pk),
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no puede ser negativo")
        self.assertFalse(Secuencial.objects.exists())

    # ------------------------------------------------------------ certificado

    def _subir_certificado(self, clave: str = CLAVE, la_suya: str = CLAVE):
        archivo = SimpleUploadedFile(
            "firma.p12",
            certificado_de_prueba(la_suya),
            content_type="application/x-pkcs12",
        )
        return self.client.post(
            reverse("configuracion:sri"),
            {
                "paso": "3",
                "c": str(self.configuracion.pk),
                "certificado": archivo,
                "clave_certificado": clave,
            },
        )

    def test_el_certificado_se_guarda_con_la_contraseña_cifrada(self):
        respuesta = self._subir_certificado()
        self.assertRedirects(respuesta, self.url(4), fetch_redirect_response=False)
        self.configuracion.refresh_from_db()
        self.assertTrue(self.configuracion.certificado)
        self.assertEqual(self.configuracion.obtener_clave(), CLAVE)
        self.assertNotIn(CLAVE, self.configuracion.clave_certificado_cifrada)

    def test_con_la_contraseña_equivocada_no_se_guarda(self):
        respuesta = self._subir_certificado(clave="otra-cosa")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo abrir el certificado")
        self.configuracion.refresh_from_db()
        self.assertFalse(self.configuracion.certificado)
        self.assertEqual(self.configuracion.clave_certificado_cifrada, "")

    def test_sin_certificado_lo_dice(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {"paso": "3", "c": str(self.configuracion.pk), "clave_certificado": CLAVE},
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Adjunte el archivo de firma")

    # --------------------------------------------------------------- comprobar

    def test_el_paso_cuatro_ensena_lo_que_le_falta(self):
        respuesta = self.client.get(self.url(4))
        self.assertContains(respuesta, "sri_fe.W002")  # falta el certificado

    def test_con_todo_puesto_el_paso_cuatro_esta_conforme(self):
        self._subir_certificado()
        respuesta = self.client.get(self.url(4))
        self.assertContains(respuesta, "Ni un reparo")
        self.assertContains(respuesta, RAZON_SOCIAL)

    def test_probar_la_conexion_pregunta_por_el_ruc(self):
        with patch(
            "configuracion.views.sri_datos.consultar_datos",
            return_value=resultado_del_sri(),
        ) as consulta:
            respuesta = self.client.post(
                reverse("configuracion:probar_sri"), {"c": str(self.configuracion.pk)}
            )
        # Sin seguir el redirect: los mensajes se leen al pintar el paso 4.
        self.assertRedirects(respuesta, self.url(4), fetch_redirect_response=False)
        consulta.assert_called_once_with(RUC)
        self.assertContains(self.client.get(self.url(4)), "El SRI respondió")

    def test_si_no_hay_conexion_con_el_sri_se_dice(self):
        with patch(
            "configuracion.views.sri_datos.consultar_datos",
            side_effect=ErrorFacturacion("sin red"),
        ):
            self.client.post(
                reverse("configuracion:probar_sri"), {"c": str(self.configuracion.pk)}
            )
        self.assertContains(self.client.get(self.url(4)), "No se pudo contactar con el SRI")

    # ------------------------------------------------- otras configuraciones

    def test_la_segunda_configuracion_copia_el_emisor(self):
        respuesta = self.client.post(reverse("configuracion:otra"))
        self.assertEqual(ConfiguracionEmisor.objects.count(), 2)
        nueva = ConfiguracionEmisor.objects.get(ambiente=2)
        self.assertRedirects(respuesta, f"{reverse('configuracion:sri')}?paso=1&c={nueva.pk}")
        self.assertEqual(nueva.ruc, self.configuracion.ruc)
        self.assertEqual(nueva.razon_social, self.configuracion.razon_social)
        self.assertTrue(nueva.activo)
        # La de pruebas sigue activa en su ambiente: una por ambiente.
        self.configuracion.refresh_from_db()
        self.assertTrue(self.configuracion.activo)

    def test_el_menu_lleva_al_asistente(self):
        respuesta = self.client.get(reverse("facturacion:tablero"))
        self.assertContains(respuesta, reverse("configuracion:sri"))

    def test_el_cambio_de_configuracion_se_respeta(self):
        otra = ConfiguracionEmisor.objects.create(
            nombre="Producción", ambiente=2, ruc=RUC, razon_social="OTRA S.A.",
            dir_matriz="AQUÍ", estab="001", pto_emi="001",
        )
        respuesta = self.client.get(f"{reverse('configuracion:sri')}?paso=1&c={otra.pk}")
        self.assertContains(respuesta, "OTRA S.A.")


@override_settings(MEDIA_ROOT=MEDIA_DE_PRUEBA)
class AsistenteSinConfiguracionTests(TestCase):
    """El asistente cuando todavía no hay nada configurado."""

    def setUp(self) -> None:
        usuario = get_user_model().objects.create_user("prueba", password="clave")
        self.client.force_login(usuario)

    def test_empieza_pidiendo_el_emisor(self):
        respuesta = self.client.get(reverse("configuracion:sri"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El contribuyente")

    def test_no_deja_saltarse_el_primer_paso(self):
        respuesta = self.client.get(f"{reverse('configuracion:sri')}?paso=3")
        self.assertRedirects(respuesta, f"{reverse('configuracion:sri')}?paso=1")

    def test_el_primer_paso_crea_la_configuracion(self):
        respuesta = self.client.post(
            reverse("configuracion:sri"),
            {
                "paso": "1",
                "ruc": RUC,
                "razon_social": RAZON_SOCIAL,
                "nombre_comercial": "DIZOF",
                "dir_matriz": "PANAMERICANA Y CARCHI",
                "dir_establecimiento": "",
                "regimen": "RIMPE",
                "categoria": "NEGOCIO POPULAR",
                "contribuyente_especial": "",
                "agente_retencion": "",
                "campos_adicionales": "",
            },
        )
        creada = ConfiguracionEmisor.objects.get()
        self.assertRedirects(respuesta, f"{reverse('configuracion:sri')}?paso=2&c={creada.pk}")
        self.assertEqual(creada.razon_social, RAZON_SOCIAL)
        self.assertEqual(creada.estab, "001")
        self.assertTrue(creada.activo)


class AsistenteSinSesionTests(TestCase):
    """La configuración del emisor no se enseña a quien no ha entrado."""

    def test_pide_entrar(self):
        respuesta = self.client.get(reverse("configuracion:sri"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("entrar"), respuesta["Location"])
