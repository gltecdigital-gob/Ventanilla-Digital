import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from cuentas.models import Usuario
from cuentas.pruebas import entrar_con_segundo_factor
from nucleo.models import EventoBitacora, Municipio
from simuladores.models import MensajeSimulado
from simuladores.renapo import CURP_DADA_DE_BAJA

from . import seguridad
from .models import CodigoUnUso, IdentidadVinculada, NivelConfianza, Persona, VerificacionPresencial

BUZON = "simuladores.correo.BuzonBackend"
CURP = "PEPJ900101HPLRRN02"
OTRA_CURP = "GOMA050315MPLNRNA2"


def ultimo_codigo(destino):
    mensaje = MensajeSimulado.objects.filter(destino=destino).first()
    return re.search(r"\b(\d{6})\b", mensaje.texto).group(1)


class RegistroMixin:
    def registrar(self, curp=CURP, destino="persona@example.com", medio="correo"):
        self.client.post(reverse("ciudadania:registro_curp"), {"curp": curp})
        self.client.post(reverse("ciudadania:registro_identidad"), {"nombres": "Persona de Prueba", "primer_apellido": "Simulada"})
        campos = {"medio": medio, "correo": destino} if medio == "correo" else {"medio": medio, "telefono": destino}
        self.client.post(reverse("ciudadania:registro_contacto"), campos)
        self.client.post(reverse("ciudadania:registro_codigo"), {"codigo": ultimo_codigo(destino)})
        return self.client.post(reverse("ciudadania:registro_aviso"), {"acepto": "on"})


@override_settings(DEBUG=True, EMAIL_BACKEND=BUZON)
class RegistroTests(RegistroMixin, TestCase):
    def test_registro_completo_crea_persona_nivel_1_e_inicia_sesion(self):
        respuesta = self.registrar()
        self.assertRedirects(respuesta, reverse("ciudadania:perfil"))
        persona = Persona.objects.get(curp=CURP)
        self.assertEqual(persona.nivel_confianza, NivelConfianza.BASICO)
        self.assertTrue(persona.contacto_confirmado)
        self.assertEqual(persona.correo, "persona@example.com")
        self.assertEqual(persona.nombres, "PERSONA DE PRUEBA")  # dato de RENAPO, no lo que escribió la persona
        self.assertTrue(persona.renapo_simulado)
        self.assertIsNotNone(persona.acepto_aviso)
        self.assertTrue(IdentidadVinculada.objects.filter(persona=persona, proveedor="cuenta_municipal").exists())
        perfil = self.client.get(reverse("ciudadania:perfil"))
        self.assertContains(perfil, "1 de 3")
        self.assertTrue(EventoBitacora.objects.filter(persona=persona, accion="registro_ciudadano").exists())
        self.assertTrue(EventoBitacora.objects.filter(accion="consulta_renapo").exists())

    def test_registro_con_celular(self):
        self.registrar(destino="2221234567", medio="telefono")
        self.assertEqual(Persona.objects.get(curp=CURP).telefono, "2221234567")
        self.assertTrue(MensajeSimulado.objects.filter(canal="sms", destino="2221234567").exists())

    def test_nombre_que_no_coincide_no_avanza(self):
        self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP})
        respuesta = self.client.post(reverse("ciudadania:registro_identidad"), {"nombres": "Otra", "primer_apellido": "Persona"})
        self.assertContains(respuesta, "no coincide")
        self.assertRedirects(self.client.get(reverse("ciudadania:registro_contacto")), reverse("ciudadania:registro_curp"))

    def test_nombre_con_acentos_y_minusculas_coincide(self):
        self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP})
        respuesta = self.client.post(reverse("ciudadania:registro_identidad"), {"nombres": "  persona  de prúeba ", "primer_apellido": "SIMULÁDA"})
        self.assertRedirects(respuesta, reverse("ciudadania:registro_contacto"))

    def test_no_se_puede_saltar_pasos(self):
        self.assertRedirects(self.client.get(reverse("ciudadania:registro_aviso")), reverse("ciudadania:registro_curp"))
        self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP})
        self.assertRedirects(self.client.get(reverse("ciudadania:registro_codigo")), reverse("ciudadania:registro_curp"))
        respuesta = self.client.post(reverse("ciudadania:registro_aviso"), {"acepto": "on"})
        self.assertFalse(Persona.objects.exists())
        self.assertEqual(respuesta.status_code, 302)

    def test_curp_con_error_de_dedo(self):
        respuesta = self.client.post(reverse("ciudadania:registro_curp"), {"curp": "PEPJ900101HPLRRN03"})
        self.assertContains(respuesta, "dígito verificador")
        self.assertFalse(EventoBitacora.objects.filter(accion="consulta_renapo").exists())  # ni siquiera se consulta

    def test_curp_dada_de_baja(self):
        respuesta = self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP_DADA_DE_BAJA})
        self.assertContains(respuesta, "dada de baja")

    def test_curp_ya_registrada_lleva_a_entrar(self):
        self.registrar()
        self.client.post(reverse("ciudadania:salir"))
        respuesta = self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP})
        self.assertRedirects(respuesta, reverse("ciudadania:acceso"))

    def test_registro_avisa_al_titular(self):
        self.registrar()
        self.assertTrue(MensajeSimulado.objects.filter(destino="persona@example.com", asunto__icontains="seguridad").exists())

    def test_limite_de_intentos_de_nombre(self):
        self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP})
        for _ in range(5):
            self.client.post(reverse("ciudadania:registro_identidad"), {"nombres": "X", "primer_apellido": "Y"})
        respuesta = self.client.post(reverse("ciudadania:registro_identidad"), {"nombres": "Persona de prueba", "primer_apellido": "Simulada"})
        self.assertContains(respuesta, "Se agotaron los intentos")

    def test_codigo_equivocado_cinco_veces_lo_invalida(self):
        self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP})
        self.client.post(reverse("ciudadania:registro_identidad"), {"nombres": "Persona de prueba", "primer_apellido": "Simulada"})
        self.client.post(reverse("ciudadania:registro_contacto"), {"medio": "correo", "correo": "p@example.com"})
        bueno = ultimo_codigo("p@example.com")
        malo = "000000" if bueno != "000000" else "111111"
        for _ in range(5):
            self.client.post(reverse("ciudadania:registro_codigo"), {"codigo": malo})
        respuesta = self.client.post(reverse("ciudadania:registro_codigo"), {"codigo": bueno})
        self.assertContains(respuesta, "agotaron")


@override_settings(DEBUG=True, EMAIL_BACKEND=BUZON)
class AccesoTests(RegistroMixin, TestCase):
    def setUp(self):
        self.registrar()
        self.client.post(reverse("ciudadania:salir"))

    def test_entrar_con_codigo(self):
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        respuesta = self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": ultimo_codigo("persona@example.com")})
        self.assertRedirects(respuesta, reverse("ciudadania:perfil"))

    def test_curp_sin_cuenta_recibe_la_misma_respuesta(self):
        con_cuenta = self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        sin_cuenta = self.client.post(reverse("ciudadania:acceso"), {"curp": OTRA_CURP})
        self.assertRedirects(con_cuenta, reverse("ciudadania:acceso_codigo"))
        self.assertRedirects(sin_cuenta, reverse("ciudadania:acceso_codigo"))
        respuesta = self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": "123456"})
        self.assertContains(respuesta, "venció o ya no es válido")

    def test_codigo_de_registro_no_sirve_para_entrar(self):
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        codigo_registro = seguridad.emitir_codigo(CURP, CodigoUnUso.Proposito.REGISTRO, "persona@example.com")
        self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": codigo_registro})
        self.assertRedirects(self.client.get(reverse("ciudadania:perfil")), reverse("ciudadania:entrar"))

    def test_codigo_vencido(self):
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        codigo = ultimo_codigo("persona@example.com")
        CodigoUnUso.objects.update(expira=timezone.now() - timedelta(seconds=1))
        respuesta = self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": codigo})
        self.assertContains(respuesta, "venció")

    def test_el_codigo_se_usa_una_sola_vez(self):
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        codigo = ultimo_codigo("persona@example.com")
        self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": codigo})
        self.client.post(reverse("ciudadania:salir"))
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        CodigoUnUso.objects.filter(usado=False).update(usado=True)  # el nuevo código no se usa
        respuesta = self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": codigo})
        self.assertEqual(respuesta.status_code, 200)
        self.assertRedirects(self.client.get(reverse("ciudadania:perfil")), reverse("ciudadania:entrar"))

    def test_limite_de_codigos_por_curp(self):
        for _ in range(4):  # el registro ya pidió uno
            self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        respuesta = self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        self.assertContains(respuesta, "demasiados códigos")

    def test_el_limite_no_revela_si_la_curp_tiene_cuenta(self):
        for _ in range(5):
            self.client.post(reverse("ciudadania:acceso"), {"curp": OTRA_CURP})
        respuesta = self.client.post(reverse("ciudadania:acceso"), {"curp": OTRA_CURP})
        self.assertContains(respuesta, "demasiados códigos")

    def test_la_sesion_cambia_de_llave_al_entrar(self):
        self.client.get(reverse("ciudadania:acceso"))
        antes = self.client.session.session_key
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": ultimo_codigo("persona@example.com")})
        self.assertNotEqual(self.client.session.session_key, antes)

    def test_cuenta_suspendida_no_entra(self):
        Persona.objects.update(activa=False)
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        self.assertFalse(CodigoUnUso.objects.filter(proposito="acceso").exists())


@override_settings(DEBUG=True, EMAIL_BACKEND=BUZON)
class LlaveMXTests(RegistroMixin, TestCase):
    def entrar_con_llave(self, curp=CURP, verificada=False):
        inicio = self.client.get(reverse("ciudadania:llave_mx"))
        url = urlsplit(inicio["Location"])
        parametros = parse_qs(url.query)
        respuesta = self.client.post(f"{url.path}?{url.query}", {"curp": curp, "verificada": "on" if verificada else ""})
        self.assertIn(parametros["state"][0], respuesta["Location"])
        return self.client.get(respuesta["Location"])

    def test_primer_acceso_crea_persona_nivel_2_y_pide_aviso(self):
        respuesta = self.entrar_con_llave()
        self.assertRedirects(respuesta, reverse("ciudadania:aceptar_aviso"))
        persona = Persona.objects.get(curp=CURP)
        self.assertEqual(persona.nivel_confianza, NivelConfianza.VERIFICADO)
        self.client.post(reverse("ciudadania:aceptar_aviso"), {"acepto": "on"})
        self.assertContains(self.client.get(reverse("ciudadania:perfil")), "2 de 3")

    def test_llave_verificada_da_nivel_3(self):
        self.entrar_con_llave(verificada=True)
        self.assertEqual(Persona.objects.get(curp=CURP).nivel_confianza, NivelConfianza.ALTO)

    def test_se_une_a_la_cuenta_municipal_existente(self):
        self.registrar()
        self.client.post(reverse("ciudadania:salir"))
        self.entrar_con_llave()
        self.assertEqual(Persona.objects.count(), 1)
        persona = Persona.objects.get()
        self.assertEqual(persona.identidades.count(), 2)
        self.assertEqual(persona.nivel_confianza, NivelConfianza.VERIFICADO)
        self.assertTrue(EventoBitacora.objects.filter(persona=persona, accion="vinculacion").exists())

    def test_otra_llave_mx_para_la_misma_curp_se_rechaza(self):
        self.entrar_con_llave()
        IdentidadVinculada.objects.filter(proveedor="llave_mx").update(sujeto="llavemx-otro-sujeto")
        self.client.post(reverse("ciudadania:salir"))
        respuesta = self.entrar_con_llave()
        self.assertRedirects(respuesta, reverse("ciudadania:entrar"))
        self.assertEqual(IdentidadVinculada.objects.filter(proveedor="llave_mx").count(), 1)

    def test_estado_alterado_se_rechaza(self):
        self.client.get(reverse("ciudadania:llave_mx"))
        respuesta = self.client.get(reverse("ciudadania:llave_mx_retorno") + "?state=falso&code=x")
        self.assertRedirects(respuesta, reverse("ciudadania:entrar"))
        self.assertFalse(Persona.objects.exists())

    def test_codigo_reutilizado_se_rechaza(self):
        inicio = self.client.get(reverse("ciudadania:llave_mx"))
        url = urlsplit(inicio["Location"])
        retorno = self.client.post(f"{url.path}?{url.query}", {"curp": CURP})["Location"]
        self.client.get(retorno)
        self.client.post(reverse("ciudadania:salir"))
        self.client.get(reverse("ciudadania:llave_mx"))
        session = self.client.session
        estado = session["llave_mx_estado"]
        codigo = parse_qs(urlsplit(retorno).query)["code"][0]
        respuesta = self.client.get(reverse("ciudadania:llave_mx_retorno") + f"?state={estado}&code={codigo}")
        self.assertRedirects(respuesta, reverse("ciudadania:entrar"))

    def test_sesion_municipal_no_pasa_de_nivel_2(self):
        self.entrar_con_llave(verificada=True)
        self.client.post(reverse("ciudadania:aceptar_aviso"), {"acepto": "on"})
        Persona.objects.update(correo="persona@example.com", contacto_confirmado=True)
        self.client.post(reverse("ciudadania:salir"))
        self.client.post(reverse("ciudadania:acceso"), {"curp": CURP})
        self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": ultimo_codigo("persona@example.com")})
        self.assertContains(self.client.get(reverse("ciudadania:perfil")), "2 de 3")


class SimuladoresEnProduccionTests(TestCase):
    @override_settings(DEBUG=False, PERMITIR_SIMULADORES=False)
    def test_paginas_de_simulador_no_existen_en_produccion(self):
        self.assertEqual(self.client.get(reverse("simuladores:buzon")).status_code, 404)
        self.assertEqual(self.client.get(reverse("simuladores:llave_mx_autorizar")).status_code, 404)

    @override_settings(DEBUG=True)
    def test_simulador_de_llave_solo_regresa_a_esta_plataforma(self):
        url = reverse("simuladores:llave_mx_autorizar") + "?state=x&redirect_uri=https://sitio-ajeno.example/robar"
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(DEBUG=False, RENAPO_BACKEND="convenio", ALLOWED_HOSTS=["testserver"])
    def test_sin_convenio_renapo_responde_con_mensaje_claro(self):
        respuesta = self.client.post(reverse("ciudadania:registro_curp"), {"curp": CURP}, secure=True)
        self.assertContains(respuesta, "no podemos validar tu CURP")


@override_settings(DEBUG=True, EMAIL_BACKEND=BUZON)
class VentanillaTests(RegistroMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_piloto", verbosity=0)
        cls.zacatlan = Municipio.objects.get(slug="zacatlan")

    def setUp(self):
        self.servidor = Usuario.objects.create_user(
            "ventanilla.zac", password="Clave-larga-de-prueba-1", is_staff=True,
            municipio=self.zacatlan, rol=Usuario.Rol.VENTANILLA, first_name="Ana",
        )
        self.servidor.groups.add(Group.objects.get(name="Ventanilla"))

    def verificacion(self, alta=False):
        datos = {"tipo_identificacion": "ine", "ultimos_digitos": "a1b2", "cotejo": "on"}
        if alta:
            datos["aviso"] = "on"
        return datos

    def test_requiere_permiso(self):
        sin_permiso = Usuario.objects.create_user("consulta", password="Clave-larga-de-prueba-1", is_staff=True, municipio=self.zacatlan)
        entrar_con_segundo_factor(self.client, sin_permiso)
        self.assertEqual(self.client.get(reverse("ventanilla:inicio")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("ventanilla:inicio")).status_code, 302)

    def test_alta_en_ventanilla_con_nivel_2_y_sin_contacto(self):
        entrar_con_segundo_factor(self.client, self.servidor)
        respuesta = self.client.post(reverse("ventanilla:inicio"), {"curp": OTRA_CURP})
        self.assertRedirects(respuesta, reverse("ventanilla:alta"))
        self.assertContains(self.client.get(reverse("ventanilla:alta")), "PERSONA DE PRUEBA")
        respuesta = self.client.post(reverse("ventanilla:alta"), self.verificacion(alta=True))
        persona = Persona.objects.get(curp=OTRA_CURP)
        self.assertRedirects(respuesta, reverse("ventanilla:contacto", args=[OTRA_CURP]))
        self.assertEqual(persona.nivel_confianza, NivelConfianza.VERIFICADO)
        self.assertFalse(persona.contacto_confirmado)
        self.assertIsNotNone(persona.acepto_aviso)
        verificacion = VerificacionPresencial.objects.get(persona=persona)
        self.assertEqual(verificacion.ultimos_digitos, "A1B2")
        self.assertEqual(verificacion.servidor, self.servidor)
        evento = EventoBitacora.objects.get(persona=persona, accion="verificacion")
        self.assertEqual(evento.usuario, self.servidor)
        self.assertEqual(evento.municipio, self.zacatlan)

    def test_sin_cotejo_no_se_verifica(self):
        entrar_con_segundo_factor(self.client, self.servidor)
        self.client.post(reverse("ventanilla:inicio"), {"curp": OTRA_CURP})
        datos = self.verificacion(alta=True)
        del datos["cotejo"]
        self.client.post(reverse("ventanilla:alta"), datos)
        self.assertFalse(Persona.objects.exists())

    def test_confirmar_contacto_en_ventanilla_permite_entrar_en_linea(self):
        entrar_con_segundo_factor(self.client, self.servidor)
        self.client.post(reverse("ventanilla:inicio"), {"curp": OTRA_CURP})
        self.client.post(reverse("ventanilla:alta"), self.verificacion(alta=True))
        url = reverse("ventanilla:contacto", args=[OTRA_CURP])
        self.client.post(url, {"accion": "enviar", "medio": "telefono", "telefono": "776 123 4567"})
        self.client.post(url, {"accion": "verificar", "codigo": ultimo_codigo("7761234567")})
        persona = Persona.objects.get(curp=OTRA_CURP)
        self.assertTrue(persona.contacto_confirmado)
        self.assertEqual(persona.telefono, "7761234567")
        # Ahora la persona entra desde su casa con nivel 2
        self.client.logout()
        self.client.post(reverse("ciudadania:acceso"), {"curp": OTRA_CURP})
        self.client.post(reverse("ciudadania:acceso_codigo"), {"codigo": ultimo_codigo("7761234567")})
        perfil = self.client.get(reverse("ciudadania:perfil"))
        self.assertContains(perfil, "2 de 3")
        self.assertContains(perfil, "Personal de Zacatlán")  # ve quién consultó sus datos

    def test_verificar_a_persona_registrada_en_linea_sube_su_nivel(self):
        self.registrar()
        self.client.post(reverse("ciudadania:salir"))
        entrar_con_segundo_factor(self.client, self.servidor)
        respuesta = self.client.post(reverse("ventanilla:inicio"), {"curp": CURP})
        self.assertRedirects(respuesta, reverse("ventanilla:persona", args=[CURP]))
        self.client.get(respuesta["Location"])
        self.assertTrue(EventoBitacora.objects.filter(accion="consulta_datos", usuario=self.servidor).exists())
        self.client.post(reverse("ventanilla:persona", args=[CURP]), self.verificacion())
        self.assertEqual(Persona.objects.get(curp=CURP).nivel_confianza, NivelConfianza.VERIFICADO)
        self.assertTrue(MensajeSimulado.objects.filter(destino="persona@example.com", texto__icontains="ventanilla").exists())


class SeguridadTests(TestCase):
    def test_enmascarado(self):
        self.assertEqual(seguridad.enmascarar_correo("juana@example.com"), "ju••••@example.com")
        self.assertEqual(seguridad.enmascarar_telefono("7761234567"), "••••••4567")
        self.assertEqual(seguridad.enmascarar_curp(CURP), "PEPJ••••••••••RN02")

    def test_el_codigo_no_se_guarda_en_claro(self):
        codigo = seguridad.emitir_codigo(CURP, "acceso", "x@example.com")
        self.assertNotIn(codigo, CodigoUnUso.objects.get().huella)

    def test_slug_reservado(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            Municipio(nombre="Cuenta", slug="cuenta").full_clean()
