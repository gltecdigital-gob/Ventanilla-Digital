from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from nucleo.models import Municipio

from .models import Requisito, Tramite


class CatalogoPublicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_piloto", verbosity=0)
        cls.zacatlan = Municipio.objects.get(slug="zacatlan")

    def test_inicio_lista_los_municipios(self):
        respuesta = self.client.get(reverse("catalogo:inicio"))
        self.assertContains(respuesta, "Zacatlán")
        self.assertContains(respuesta, "Huauchinango")

    def test_catalogo_pagina_de_30_en_30(self):
        respuesta = self.client.get(reverse("catalogo:catalogo", args=["zacatlan"]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["pagina"]), 30)
        self.assertEqual(respuesta.context["total"], 90)

    def test_busqueda_encuentra_por_nombre(self):
        respuesta = self.client.get(reverse("catalogo:catalogo", args=["zacatlan"]), {"q": "constancia"})
        self.assertGreater(respuesta.context["total"], 5)
        for tramite in respuesta.context["pagina"]:
            self.assertIn("onstancia", tramite.nombre)

    def test_catalogo_no_mezcla_municipios(self):
        respuesta = self.client.get(reverse("catalogo:catalogo", args=["zacatlan"]), {"q": "agua"})
        for tramite in respuesta.context["pagina"]:
            self.assertEqual(tramite.municipio, self.zacatlan)
        ajeno = Tramite.objects.filter(municipio__slug="huauchinango").first()
        respuesta = self.client.get(reverse("catalogo:ficha", args=["zacatlan", ajeno.clave]))
        self.assertEqual(respuesta.status_code, 404)

    def test_ficha_incompleta_avisa_que_esta_en_levantamiento(self):
        tramite = Tramite.objects.filter(municipio=self.zacatlan).first()
        respuesta = self.client.get(tramite.get_absolute_url())
        self.assertContains(respuesta, "Ficha en levantamiento")

    def test_tramite_archivado_no_se_muestra(self):
        tramite = Tramite.objects.filter(municipio=self.zacatlan).first()
        tramite.estatus = Tramite.Estatus.ARCHIVADO
        tramite.save()
        self.assertEqual(self.client.get(tramite.get_absolute_url()).status_code, 404)

    def test_municipio_inexistente_da_404(self):
        self.assertEqual(self.client.get("/no-existe/").status_code, 404)

    def test_la_busqueda_no_ejecuta_codigo_incrustado(self):
        respuesta = self.client.get(reverse("catalogo:catalogo", args=["zacatlan"]), {"q": "<script>alert(1)</script>"})
        self.assertNotContains(respuesta, "<script>alert(1)</script>")


class PublicacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_piloto", verbosity=0)

    def setUp(self):
        self.tramite = Tramite.objects.get(clave="T04MZACSGAT2026")

    def test_no_se_publica_una_ficha_incompleta(self):
        self.tramite.estatus = Tramite.Estatus.PUBLICADO
        with self.assertRaises(ValidationError) as error:
            self.tramite.full_clean()
        self.assertIn("fundamento jurídico", str(error.exception))

    def test_se_publica_cuando_esta_completa(self):
        t = self.tramite
        t.descripcion = "Documento que acredita dónde vives."
        t.fundamento = "Ley Orgánica Municipal, art. 138 fr. VII (ejemplo de prueba)"
        t.plazo_resolucion_dias = 1
        t.costo = 0
        t.oficinas = "Secretaría del Ayuntamiento, Palacio Municipal"
        t.contacto = "797 124 57 71"
        t.estatus = Tramite.Estatus.PUBLICADO
        t.full_clean()
        t.save()
        respuesta = self.client.get(t.get_absolute_url())
        self.assertNotContains(respuesta, "Ficha en levantamiento")
        self.assertContains(respuesta, "Gratuito")
        self.assertContains(respuesta, "1 día hábil")

    def test_alertas_de_requisito(self):
        requisito = Requisito(tramite=self.tramite, nombre="Constancia de no adeudo predial",
                              formato=Requisito.Formato.COPIA_SIMPLE, quien_expide=Requisito.Expide.MUNICIPIO)
        self.assertEqual(len(requisito.alertas()), 3)
