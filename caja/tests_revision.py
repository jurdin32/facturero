"""Pruebas de la revisión de los cuadres y de los vales de caja.

Lo que se comprueba aquí es el control interno del efectivo: que un cuadre cerrado
se pueda aprobar o dejar observado dejando dicho quién lo revisó, y que el faltante
se cobre con un vale que nace pendiente, se cobra o se anula —sin que el vale pueda
inventar más faltante del que hubo—.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import servicios
from .models import SesionCaja, ValeCaja


class BaseDeCaja(TestCase):
    """Un turno cerrado con faltante, que es el caso que se revisa."""

    def setUp(self) -> None:
        Usuario = get_user_model()
        self.cajero = Usuario.objects.create_user("cajero", password="clave-larga-1")
        self.supervisor = Usuario.objects.create_user("supervisor", password="clave-larga-2")
        self.supervisor.is_superuser = True
        self.supervisor.save()

        self.sesion = servicios.abrir(self.cajero, Decimal("50.00"), "turno de prueba")
        servicios.registrar_movimiento(
            self.sesion,
            self.cajero,
            tipo="ingreso",
            concepto="factura 1",
            importe=Decimal("30.00"),
        )
        # Se cuenta 70 cuando se esperaban 80: faltan 10.
        servicios.cerrar(self.sesion, Decimal("70.00"), "faltaron diez")
        self.sesion.refresh_from_db()

        self.cliente = Client(SERVER_NAME="localhost")

    def entrar(self, usuario) -> None:
        self.cliente.force_login(usuario)


class RevisionDelCuadre(BaseDeCaja):
    def test_un_turno_cerrado_nace_sin_revisar(self) -> None:
        self.assertEqual(self.sesion.revision, "sin_revisar")
        self.assertIsNone(self.sesion.revisada_por)

    def test_aprobar_anota_quien_y_cuando(self) -> None:
        servicios.revisar(self.sesion, self.supervisor, "aprobada", "cuadra con la factura")

        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.revision, "aprobada")
        self.assertEqual(self.sesion.revisada_por, self.supervisor)
        self.assertIsNotNone(self.sesion.revisada_en)
        self.assertEqual(self.sesion.nota_revision, "cuadra con la factura")

    def test_observar_guarda_la_nota(self) -> None:
        servicios.revisar(self.sesion, self.supervisor, "observada", "falta el comprobante")

        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.revision, "observada")
        self.assertEqual(self.sesion.nota_revision, "falta el comprobante")

    def test_una_decision_inventada_no_vale(self) -> None:
        with self.assertRaises(ValidationError):
            servicios.revisar(self.sesion, self.supervisor, "aprobadísima")

    def test_no_se_revisa_una_caja_abierta(self) -> None:
        abierta = servicios.abrir(self.supervisor, Decimal("10.00"))
        with self.assertRaises(ValidationError):
            servicios.revisar(abierta, self.supervisor, "aprobada")

    def test_la_pantalla_ensena_los_cuadres_cerrados(self) -> None:
        self.entrar(self.supervisor)

        respuesta = self.cliente.get(reverse("supervision:cuadres"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Revisión de caja")
        self.assertContains(respuesta, "Falta")

    def test_aprobar_desde_la_pantalla(self) -> None:
        self.entrar(self.supervisor)

        respuesta = self.cliente.post(
            reverse("supervision:cuadres"),
            {"sesion": self.sesion.pk, "decision": "aprobada", "nota": "todo en orden"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.revision, "aprobada")
        self.assertEqual(self.sesion.nota_revision, "todo en orden")

    def test_el_filtro_deja_fuera_lo_aprobado(self) -> None:
        servicios.revisar(self.sesion, self.supervisor, "aprobada")
        self.entrar(self.supervisor)

        respuesta = self.cliente.get(reverse("supervision:cuadres"), {"revision": "sin_revisar"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, f'name="sesion" value="{self.sesion.pk}"')


class ValesDeCaja(BaseDeCaja):
    def hacer_vale(self, importe: str = "10.00", **extra):
        datos = {
            "responsable": self.cajero,
            "importe": Decimal(importe),
            "motivo": "Faltante del turno",
            "tipo": ValeCaja.Tipo.FALTANTE.value,
            "sesion": self.sesion,
            "creado_por": self.supervisor,
        }
        datos.update(extra)
        return servicios.crear_vale(**datos)

    def test_el_vale_nace_pendiente_y_numerado(self) -> None:
        vale = self.hacer_vale()

        self.assertEqual(vale.estado, ValeCaja.Estado.PENDIENTE.value)
        self.assertEqual(vale.numero, "VC-000001")
        self.assertEqual(vale.responsable, self.cajero)

    def test_el_segundo_vale_sigue_la_numeracion(self) -> None:
        self.hacer_vale("4.00")
        otro = self.hacer_vale("6.00")

        self.assertEqual(otro.numero, "VC-000002")

    def test_no_se_puede_cobrar_mas_que_el_faltante(self) -> None:
        with self.assertRaises(ValidationError):
            self.hacer_vale("25.00")

    def test_los_vales_no_pasan_del_faltante_entre_varios(self) -> None:
        self.hacer_vale("6.00")

        with self.assertRaises(ValidationError):
            self.hacer_vale("6.00")

    def test_sobre_una_caja_sin_faltante_no_hay_nada_que_cobrar(self) -> None:
        # Un turno que cuadra: se cuenta exactamente lo que se esperaba.
        justa = servicios.abrir(self.supervisor, Decimal("20.00"))
        servicios.cerrar(justa, Decimal("20.00"))
        justa.refresh_from_db()

        with self.assertRaises(ValidationError):
            self.hacer_vale("1.00", sesion=justa)

    def test_el_importe_tiene_que_ser_positivo(self) -> None:
        with self.assertRaises(ValidationError):
            self.hacer_vale("0.00")

    def test_cobrar_un_vale_lo_cierra_con_fecha(self) -> None:
        vale = self.hacer_vale()

        servicios.cobrar_vale(vale, "pagó en efectivo")

        vale.refresh_from_db()
        self.assertEqual(vale.estado, ValeCaja.Estado.COBRADO.value)
        self.assertEqual(vale.cobrado_en, timezone.localdate())
        self.assertIn("pagó en efectivo", vale.nota)

    def test_no_se_cobra_dos_veces(self) -> None:
        vale = self.hacer_vale()
        servicios.cobrar_vale(vale)

        with self.assertRaises(ValidationError):
            servicios.cobrar_vale(vale)

    def test_anular_lo_deja_anulado(self) -> None:
        vale = self.hacer_vale()

        servicios.anular_vale(vale, "se equivocó el conteo")

        vale.refresh_from_db()
        self.assertEqual(vale.estado, ValeCaja.Estado.ANULADO.value)

    def test_un_vale_anulado_no_cuenta_contra_el_faltante(self) -> None:
        viejo = self.hacer_vale("10.00")
        servicios.anular_vale(viejo)

        nuevo = self.hacer_vale("10.00")

        self.assertEqual(nuevo.importe, Decimal("10.00"))

    def test_la_pantalla_de_vales_ensena_lo_pendiente(self) -> None:
        self.hacer_vale()
        self.entrar(self.supervisor)

        respuesta = self.cliente.get(reverse("supervision:vales"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "VC-000001")
        self.assertContains(respuesta, "Pendiente")

    def test_crear_un_vale_desde_la_pantalla(self) -> None:
        self.entrar(self.supervisor)

        respuesta = self.cliente.post(
            reverse("supervision:vale_de_la_sesion", args=[self.sesion.pk]),
            {
                "responsable": self.cajero.pk,
                "tipo": ValeCaja.Tipo.FALTANTE.value,
                "importe": "10.00",
                "motivo": "Faltante del turno",
                "nota": "se descuenta del sueldo",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        vale = ValeCaja.objects.get()
        self.assertEqual(vale.numero, "VC-000001")
        self.assertEqual(vale.sesion, self.sesion)
        self.assertEqual(vale.creado_por, self.supervisor)

    def test_el_formulario_trae_el_faltante_puesto(self) -> None:
        self.entrar(self.supervisor)

        respuesta = self.cliente.get(reverse("supervision:vale_de_la_sesion", args=[self.sesion.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "10.00")

    def test_cobrar_desde_la_pantalla(self) -> None:
        vale = self.hacer_vale()
        self.entrar(self.supervisor)

        respuesta = self.cliente.post(
            reverse("supervision:vales"), {"vale": vale.pk, "que": "cobrar", "nota": "efectivo"}
        )

        self.assertEqual(respuesta.status_code, 302)
        vale.refresh_from_db()
        self.assertEqual(vale.estado, ValeCaja.Estado.COBRADO.value)


CERRADO = {"MODO": "cerrado", "SUPERUSUARIOS_TODO": True}


class PermisosDeLaRevision(TestCase):
    """Con el paquete en modo cerrado: leer se lee, escribir pide su permiso."""

    def setUp(self) -> None:
        from personalize_options.models import Nivel, Permiso, Rol

        self.cajero = get_user_model().objects.create_user("cajero2", password="clave-larga-1")
        self.sesion = servicios.abrir(self.cajero, Decimal("10.00"))
        servicios.cerrar(self.sesion, Decimal("10.00"))
        self.sesion.refresh_from_db()
        self.rol = Rol.objects.create(nombre="Supervisor")
        self.rol.usuarios.add(self.cajero)

        self.cliente = Client(SERVER_NAME="localhost")
        self.cliente.force_login(self.cajero)
        self._Permiso = Permiso
        self._Nivel = Nivel

    def _dar(self, nivel: str, opcion: str = "revision_caja") -> None:
        self._Permiso.objects.create(rol=self.rol, opcion=opcion, nivel=nivel)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_sin_permiso_no_se_entra(self) -> None:
        self.assertEqual(self.cliente.get(reverse("supervision:cuadres")).status_code, 403)
        self.assertEqual(self.cliente.get(reverse("supervision:vales")).status_code, 403)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_la_caja_del_turno_no_da_la_revision(self) -> None:
        # Tener la caja —aunque sea con escritura— no es tener la supervisión.
        self._dar(self._Nivel.ESCRITURA.value, opcion="caja")

        self.assertEqual(self.cliente.get(reverse("supervision:cuadres")).status_code, 403)
        self.assertEqual(self.cliente.get(reverse("supervision:vales")).status_code, 403)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_con_lectura_se_mira_pero_no_se_aprueba(self) -> None:
        self._dar(self._Nivel.LECTURA.value)
        self._dar(self._Nivel.LECTURA.value, opcion="vales_caja")

        self.assertEqual(self.cliente.get(reverse("supervision:cuadres")).status_code, 200)
        self.assertEqual(self.cliente.get(reverse("supervision:vales")).status_code, 200)
        # El botón de aprobar no se pinta.
        self.assertNotContains(self.cliente.get(reverse("supervision:cuadres")), "Aprobar el cuadre")

        respuesta = self.cliente.post(
            reverse("supervision:cuadres"), {"sesion": self.sesion.pk, "decision": "aprobada"}
        )

        self.assertEqual(respuesta.status_code, 403)
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.revision, "sin_revisar")

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_con_escritura_se_aprueba(self) -> None:
        self._dar(self._Nivel.ESCRITURA.value)

        respuesta = self.cliente.post(
            reverse("supervision:cuadres"), {"sesion": self.sesion.pk, "decision": "aprobada"}
        )

        self.assertEqual(respuesta.status_code, 302)
        self.sesion.refresh_from_db()
        self.assertEqual(self.sesion.revision, "aprobada")

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_quien_revisa_puede_bajar_el_acta(self) -> None:
        # El acta se firma en la revisión: hay que poder abrirla sin ser el dueño
        # de la caja.
        self._dar(self._Nivel.LECTURA.value)

        respuesta = self.cliente.get(reverse("caja:acta", args=[self.sesion.pk]))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_el_dueno_de_la_caja_tambien_baja_su_acta(self) -> None:
        self._dar(self._Nivel.LECTURA.value, opcion="caja")

        respuesta = self.cliente.get(reverse("caja:acta", args=[self.sesion.pk]))

        self.assertEqual(respuesta.status_code, 200)

    @override_settings(PERSONALIZE_OPTIONS=CERRADO)
    def test_sin_ninguno_de_los_dos_permisos_no_hay_acta(self) -> None:
        self._dar(self._Nivel.LECTURA.value, opcion="clientes")

        respuesta = self.cliente.get(reverse("caja:acta", args=[self.sesion.pk]))

        self.assertEqual(respuesta.status_code, 403)
