from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalogo.models import Tramite
from cuentas.models import Usuario
from nucleo.models import Dependencia, EventoBitacora, Municipio


class BasePiloto(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_piloto", verbosity=0)
        cls.zacatlan = Municipio.objects.get(slug="zacatlan")
        cls.huauchinango = Municipio.objects.get(slug="huauchinango")

    def crear_usuario(self, nombre, municipio, grupo, rol, dependencia=None):
        usuario = Usuario.objects.create_user(
            nombre, password="Clave-larga-de-prueba-1", is_staff=True,
            municipio=municipio, rol=rol, dependencia=dependencia,
        )
        usuario.groups.add(Group.objects.get(name=grupo))
        return usuario


class CargaPilotoTests(BasePiloto):
    def test_carga_los_dos_municipios(self):
        self.assertEqual(Tramite.objects.filter(municipio=self.zacatlan).count(), 90)
        self.assertEqual(Tramite.objects.filter(municipio=self.huauchinango).count(), 112)

    def test_repetir_la_carga_no_duplica_ni_pisa_ediciones(self):
        tramite = Tramite.objects.filter(municipio=self.zacatlan).first()
        tramite.nombre = "Nombre corregido por el Enlace"
        tramite.save()
        call_command("cargar_piloto", verbosity=0)
        self.assertEqual(Tramite.objects.count(), 202)
        tramite.refresh_from_db()
        self.assertEqual(tramite.nombre, "Nombre corregido por el Enlace")


class SeparacionPorMunicipioTests(BasePiloto):
    def setUp(self):
        self.autoridad = self.crear_usuario("autoridad.zac", self.zacatlan, "Autoridad Municipal", Usuario.Rol.AUTORIDAD)
        self.client.force_login(self.autoridad)

    def test_lista_solo_muestra_su_municipio(self):
        respuesta = self.client.get(reverse("admin:catalogo_tramite_changelist"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["cl"].result_count, 90)

    def test_no_puede_abrir_un_tramite_de_otro_municipio(self):
        ajeno = Tramite.objects.filter(municipio=self.huauchinango).first()
        respuesta = self.client.get(reverse("admin:catalogo_tramite_change", args=[ajeno.pk]))
        self.assertNotEqual(respuesta.status_code, 200)

    def test_no_puede_crear_un_tramite_en_otro_municipio(self):
        dependencia_ajena = Dependencia.objects.filter(municipio=self.huauchinango).first()
        datos = {
            "municipio": self.huauchinango.pk, "clave": "INTRUSO-1", "nombre": "Trámite intruso", "tipo": "tramite",
            "dependencia": dependencia_ajena.pk, "canal": "presencial", "ficta": "no_aplica",
            "nivel_confianza": 1, "estatus": "inventariado",
            "requisitos-TOTAL_FORMS": 0, "requisitos-INITIAL_FORMS": 0,
        }
        self.client.post(reverse("admin:catalogo_tramite_add"), datos)
        self.assertFalse(Tramite.objects.filter(clave="INTRUSO-1").exists())

    def test_lo_que_crea_queda_en_su_municipio(self):
        dependencia = Dependencia.objects.filter(municipio=self.zacatlan).first()
        datos = {
            "municipio": self.huauchinango.pk,  # intento de manipular el formulario
            "clave": "ZAC-NUEVO", "nombre": "Trámite nuevo", "tipo": "tramite",
            "dependencia": dependencia.pk, "canal": "presencial", "ficta": "no_aplica",
            "nivel_confianza": 1, "estatus": "inventariado",
            "requisitos-TOTAL_FORMS": 0, "requisitos-INITIAL_FORMS": 0,
        }
        respuesta = self.client.post(reverse("admin:catalogo_tramite_add"), datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Tramite.objects.get(clave="ZAC-NUEVO").municipio, self.zacatlan)

    def test_bitacora_solo_muestra_su_municipio(self):
        EventoBitacora.objects.create(accion="crear", descripcion="evento ajeno", municipio=self.huauchinango)
        EventoBitacora.objects.create(accion="crear", descripcion="evento propio", municipio=self.zacatlan)
        respuesta = self.client.get(reverse("admin:nucleo_eventobitacora_changelist"))
        self.assertContains(respuesta, "evento propio")
        self.assertNotContains(respuesta, "evento ajeno")

    def test_los_filtros_no_revelan_dependencias_de_otro_municipio(self):
        respuesta = self.client.get(reverse("admin:catalogo_tramite_changelist"))
        self.assertContains(respuesta, "Sindicatura Municipal")  # dependencia de Zacatlán
        self.assertNotContains(respuesta, "Organismo de agua")  # dependencia de Huauchinango
        self.assertNotContains(respuesta, "Huauchinango")

    def test_no_ve_usuarios_de_otro_municipio(self):
        self.crear_usuario("autoridad.hua", self.huauchinango, "Autoridad Municipal", Usuario.Rol.AUTORIDAD)
        respuesta = self.client.get(reverse("admin:cuentas_usuario_changelist"))
        self.assertContains(respuesta, "autoridad.zac")
        self.assertNotContains(respuesta, "autoridad.hua")


class EnlaceTests(BasePiloto):
    def test_enlace_solo_ve_los_tramites_de_su_dependencia(self):
        secretaria = Dependencia.objects.get(municipio=self.zacatlan, nombre="Secretaría")
        enlace = self.crear_usuario("enlace.sec", self.zacatlan, "Enlace de dependencia", Usuario.Rol.ENLACE, secretaria)
        self.client.force_login(enlace)
        respuesta = self.client.get(reverse("admin:catalogo_tramite_changelist"))
        esperado = Tramite.objects.filter(dependencia=secretaria).count()
        self.assertEqual(respuesta.context["cl"].result_count, esperado)
        self.assertEqual(esperado, 12)


class BitacoraTests(BasePiloto):
    def test_la_bitacora_no_se_modifica_ni_se_borra(self):
        evento = EventoBitacora.objects.create(accion="crear", descripcion="prueba")
        evento.descripcion = "alterado"
        with self.assertRaises(PermissionError):
            evento.save()
        with self.assertRaises(PermissionError):
            evento.delete()

    def test_editar_un_tramite_deja_rastro(self):
        autoridad = self.crear_usuario("autoridad.zac", self.zacatlan, "Autoridad Municipal", Usuario.Rol.AUTORIDAD)
        self.client.force_login(autoridad)
        tramite = Tramite.objects.filter(municipio=self.zacatlan).first()
        datos = {
            "clave": tramite.clave, "nombre": tramite.nombre + " (editado)", "tipo": tramite.tipo,
            "dependencia": tramite.dependencia_id, "canal": tramite.canal, "ficta": tramite.ficta,
            "nivel_confianza": tramite.nivel_confianza, "estatus": tramite.estatus, "ruta": tramite.ruta,
            "requisitos-TOTAL_FORMS": 0, "requisitos-INITIAL_FORMS": 0,
        }
        respuesta = self.client.post(reverse("admin:catalogo_tramite_change", args=[tramite.pk]), datos)
        self.assertEqual(respuesta.status_code, 302)
        evento = EventoBitacora.objects.filter(accion="modificar", objeto_id=str(tramite.pk)).first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.usuario, autoridad)
        self.assertEqual(evento.municipio, self.zacatlan)
        self.assertIn("nombre", evento.cambios["campos"])

    def test_el_inicio_de_sesion_y_el_intento_fallido_quedan_anotados(self):
        self.crear_usuario("autoridad.zac", self.zacatlan, "Autoridad Municipal", Usuario.Rol.AUTORIDAD)
        self.client.login(username="autoridad.zac", password="incorrecta")
        self.client.login(username="autoridad.zac", password="Clave-larga-de-prueba-1")
        self.assertTrue(EventoBitacora.objects.filter(accion="acceso_fallido").exists())
        self.assertTrue(EventoBitacora.objects.filter(accion="acceso").exists())
