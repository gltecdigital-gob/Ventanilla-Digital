import hashlib
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from nucleo.models import EventoBitacora, Municipio

from . import segundo_factor as sf
from . import totp
from .models import CodigoRespaldo, SegundoFactor, Usuario
from .pruebas import codigo_vigente, entrar_con_segundo_factor

CLAVE = "Clave-larga-de-prueba-1"


class TotpTests(SimpleTestCase):
    """Vectores de prueba del RFC 6238 (SHA-1, 8 dígitos)."""

    SEMILLA = b"12345678901234567890"

    def test_vectores_rfc_6238(self):
        casos = {59: "94287082", 1111111109: "07081804", 1111111111: "14050471",
                 1234567890: "89005924", 2000000000: "69279037", 20000000000: "65353130"}
        for segundos, esperado in casos.items():
            self.assertEqual(totp.codigo("", segundos // 30, digitos=8, algoritmo=hashlib.sha1, clave=self.SEMILLA), esperado)

    def test_acepta_desfase_de_un_periodo_y_no_mas(self):
        secreto = totp.generar_secreto()
        ahora = 1_800_000_000
        paso = totp.paso_actual(ahora)
        self.assertEqual(totp.verificar(secreto, totp.codigo(secreto, paso - 1), ahora=ahora), paso - 1)
        self.assertEqual(totp.verificar(secreto, totp.codigo(secreto, paso + 1), ahora=ahora), paso + 1)
        self.assertIsNone(totp.verificar(secreto, totp.codigo(secreto, paso - 2), ahora=ahora))

    def test_no_acepta_un_paso_ya_usado(self):
        secreto = totp.generar_secreto()
        ahora = 1_800_000_000
        paso = totp.paso_actual(ahora)
        self.assertIsNone(totp.verificar(secreto, totp.codigo(secreto, paso), ultimo_paso_usado=paso, ahora=ahora))

    def test_rechaza_formatos_invalidos(self):
        secreto = totp.generar_secreto()
        for malo in ("", "12345", "1234567", "abcdef", None):
            self.assertIsNone(totp.verificar(secreto, malo))

    def test_uri_para_la_aplicacion(self):
        uri = totp.uri_aprovisionamiento("ABCDEF", "ana.lopez", "Tramites municipales")
        self.assertTrue(uri.startswith("otpauth://totp/Tramites%20municipales%3Aana.lopez?"))
        self.assertIn("secret=ABCDEF", uri)


class SegundoFactorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_piloto", verbosity=0)
        cls.zacatlan = Municipio.objects.get(slug="zacatlan")

    def setUp(self):
        self.usuario = Usuario.objects.create_user("ana.zac", password=CLAVE, is_staff=True,
                                                   municipio=self.zacatlan, rol=Usuario.Rol.AUTORIDAD)
        self.usuario.groups.add(Group.objects.get(name="Autoridad Municipal"))

    def entrar(self):
        self.client.post(reverse("admin:login"), {"username": "ana.zac", "password": CLAVE})

    def activar(self):
        self.entrar()
        self.client.get(reverse("segundo_factor:configurar"))
        factor = SegundoFactor.objects.get(usuario=self.usuario)
        respuesta = self.client.post(reverse("segundo_factor:configurar"), {"codigo": codigo_vigente(factor), "next": "/panel/"})
        return factor, respuesta

    def test_sin_segundo_factor_no_entra_al_panel_ni_a_la_ventanilla(self):
        self.entrar()
        respuesta = self.client.get("/panel/catalogo/tramite/")
        self.assertRedirects(respuesta, reverse("segundo_factor:configurar") + "?next=/panel/catalogo/tramite/", fetch_redirect_response=False)
        respuesta = self.client.get("/ventanilla/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("segundo-factor", respuesta["Location"])

    def test_activacion_muestra_qr_y_entrega_codigos_de_respaldo(self):
        self.entrar()
        pagina = self.client.get(reverse("segundo_factor:configurar"))
        self.assertContains(pagina, "<svg")
        self.assertNotContains(pagina, "Trámites y servicios")  # sin menú del panel antes de verificar
        factor, respuesta = self.activar()
        self.assertContains(respuesta, "Solo se muestran esta vez")
        self.assertEqual(len(respuesta.context["codigos"]), 10)
        self.assertEqual(CodigoRespaldo.objects.filter(usuario=self.usuario).count(), 10)
        self.assertEqual(self.client.get("/panel/").status_code, 200)
        factor.refresh_from_db()
        self.assertIsNotNone(factor.confirmado)
        self.assertTrue(EventoBitacora.objects.filter(accion="segundo_factor", usuario=self.usuario).exists())

    def test_el_secreto_se_guarda_cifrado(self):
        factor, _ = self.activar()
        factor.refresh_from_db()
        self.assertNotIn(factor.secreto, factor.secreto_cifrado)
        self.assertEqual(len(factor.secreto), 32)

    def test_codigo_incorrecto_en_activacion(self):
        self.entrar()
        self.client.get(reverse("segundo_factor:configurar"))
        respuesta = self.client.post(reverse("segundo_factor:configurar"), {"codigo": "000000"})
        self.assertContains(respuesta, "no es correcto")
        self.assertTrue(EventoBitacora.objects.filter(accion="segundo_factor_fallido").exists())
        self.assertIsNone(SegundoFactor.objects.get(usuario=self.usuario).confirmado)

    def test_cada_acceso_pide_el_codigo_y_no_se_reutiliza(self):
        factor, _ = self.activar()
        self.client.post(reverse("admin:logout"))
        self.entrar()
        self.assertIn("verificar", self.client.get("/panel/")["Location"])
        factor.refresh_from_db()
        siguiente = totp.codigo(factor.secreto, factor.ultimo_paso + 1)
        with mock.patch("cuentas.totp.paso_actual", return_value=factor.ultimo_paso + 1):
            respuesta = self.client.post(reverse("segundo_factor:verificar"), {"codigo": siguiente, "next": "/panel/"})
            self.assertRedirects(respuesta, "/panel/")
            self.client.post(reverse("admin:logout"))
            self.entrar()
            respuesta = self.client.post(reverse("segundo_factor:verificar"), {"codigo": siguiente})
        self.assertContains(respuesta, "ya se usó")

    def test_codigo_de_respaldo_sirve_una_vez(self):
        _, respuesta = self.activar()
        respaldo = respuesta.context["codigos"][0]
        self.client.post(reverse("admin:logout"))
        self.entrar()
        respuesta = self.client.post(reverse("segundo_factor:verificar"), {"codigo": respaldo.lower().replace("-", " "), "next": "/panel/"})
        self.assertRedirects(respuesta, "/panel/")
        self.client.post(reverse("admin:logout"))
        self.entrar()
        respuesta = self.client.post(reverse("segundo_factor:verificar"), {"codigo": respaldo})
        self.assertContains(respuesta, "no es correcto")

    def test_bloqueo_tras_cinco_intentos(self):
        factor, _ = self.activar()
        self.client.post(reverse("admin:logout"))
        self.entrar()
        for _ in range(5):
            self.client.post(reverse("segundo_factor:verificar"), {"codigo": "000000"})
        respuesta = self.client.post(reverse("segundo_factor:verificar"), {"codigo": codigo_vigente(factor)})
        self.assertContains(respuesta, "Demasiados intentos")

    def test_no_redirige_fuera_del_sitio(self):
        self.activar()
        self.client.post(reverse("admin:logout"))
        self.entrar()
        factor = SegundoFactor.objects.get(usuario=self.usuario)
        with mock.patch("cuentas.totp.paso_actual", return_value=factor.ultimo_paso + 1):
            respuesta = self.client.post(reverse("segundo_factor:verificar"),
                                         {"codigo": totp.codigo(factor.secreto, factor.ultimo_paso + 1), "next": "https://sitio-ajeno.example/"})
        self.assertRedirects(respuesta, "/panel/")

    def test_reiniciar_invalida_la_sesion_abierta(self):
        self.activar()
        self.assertEqual(self.client.get("/panel/").status_code, 200)
        administrador = Usuario.objects.create_superuser("admin", password=CLAVE)
        otro = self.client_class()
        entrar_con_segundo_factor(otro, administrador)
        otro.post(reverse("admin:cuentas_usuario_changelist"),
                  {"action": "reiniciar_segundo_factor", "_selected_action": [self.usuario.pk]})
        self.assertFalse(SegundoFactor.objects.filter(usuario=self.usuario).exists())
        self.assertIn("configurar", self.client.get("/panel/")["Location"])

    @override_settings(SEGUNDO_FACTOR_OBLIGATORIO=False)
    def test_se_puede_desactivar_por_configuracion(self):
        self.entrar()
        self.assertEqual(self.client.get("/panel/").status_code, 200)

    def test_la_ciudadania_no_se_ve_afectada(self):
        self.entrar()
        self.assertEqual(self.client.get("/zacatlan/").status_code, 200)
        self.assertEqual(self.client.get("/cuenta/entrar/").status_code, 200)

    def test_marca_de_sesion_depende_del_dispositivo(self):
        factor, _ = self.activar()
        self.assertEqual(self.client.session[sf.SESION], f"{self.usuario.pk}:{factor.pk}")
