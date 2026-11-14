"""Seguridad por fila: solo corre con PostgreSQL (DATABASE_URL=postgres://...)."""
import unittest
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from catalogo.admin import TramiteAdmin
from catalogo.models import Requisito, Tramite
from cuentas.models import Usuario
from cuentas.pruebas import entrar_con_segundo_factor

from . import alcance, checks
from .models import Dependencia, EventoBitacora, Municipio


@unittest.skipUnless(connection.vendor == "postgresql", "La seguridad por fila solo existe en PostgreSQL")
class SeguridadPorFilaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_piloto", verbosity=0)
        cls.zacatlan = Municipio.objects.get(slug="zacatlan")
        cls.huauchinango = Municipio.objects.get(slug="huauchinango")
        cls.tramite_hua = Tramite.objects.filter(municipio=cls.huauchinango).first()
        Requisito.objects.create(tramite=cls.tramite_hua, nombre="Requisito de Huauchinango")
        Requisito.objects.create(tramite=Tramite.objects.filter(municipio=cls.zacatlan).first(), nombre="Requisito de Zacatlán")

    def test_en_alcance_de_municipio_solo_se_ven_sus_filas(self):
        with alcance.alcance_municipio(self.zacatlan.pk):
            self.assertEqual(Tramite.objects.count(), 90)
            self.assertFalse(Dependencia.objects.exclude(municipio=self.zacatlan).exists())
            self.assertEqual(list(Municipio.objects.values_list("slug", flat=True)), ["zacatlan"])
            self.assertEqual(list(Requisito.objects.values_list("nombre", flat=True)), ["Requisito de Zacatlán"])
        self.assertEqual(Tramite.objects.count(), 202)  # al salir regresa el alcance de plataforma

    def test_no_puede_escribir_en_otro_municipio(self):
        dependencia_hua = Dependencia.objects.filter(municipio=self.huauchinango).first()
        with alcance.alcance_municipio(self.zacatlan.pk):
            with self.assertRaises(DatabaseError), transaction.atomic():
                Tramite.objects.create(municipio=self.huauchinango, dependencia=dependencia_hua, clave="X-1", nombre="Intruso")
            with self.assertRaises(DatabaseError), transaction.atomic():
                EventoBitacora.objects.create(accion="crear", descripcion="evento falso", municipio=self.huauchinango)

    def test_no_puede_modificar_ni_borrar_filas_de_otro_municipio(self):
        with alcance.alcance_municipio(self.zacatlan.pk):
            self.assertEqual(Tramite.objects.filter(pk=self.tramite_hua.pk).update(nombre="alterado"), 0)
            self.assertEqual(Requisito.objects.filter(tramite=self.tramite_hua).delete()[0], 0)
        self.tramite_hua.refresh_from_db()
        self.assertNotEqual(self.tramite_hua.nombre, "alterado")

    def test_no_puede_mover_una_fila_propia_a_otro_municipio(self):
        propio = Tramite.objects.filter(municipio=self.zacatlan).first()
        with alcance.alcance_municipio(self.zacatlan.pk):
            with self.assertRaises(DatabaseError), transaction.atomic():
                Tramite.objects.filter(pk=propio.pk).update(municipio=self.huauchinango)

    def test_sin_municipio_o_alcance_desconocido_no_se_ve_nada(self):
        alcance.fijar(alcance.MUNICIPIO, None)
        self.assertEqual(Tramite.objects.count(), 0)
        alcance.fijar("cualquier-cosa")
        self.assertEqual(Tramite.objects.count(), 0)
        alcance.fijar(alcance.PLATAFORMA)
        self.assertEqual(Tramite.objects.count(), 202)

    def test_un_error_en_el_panel_no_expone_otro_municipio(self):
        """Aunque el panel olvide filtrar por municipio, la base no entrega filas ajenas."""
        autoridad = Usuario.objects.create_user("autoridad.zac", password="Clave-larga-de-prueba-1", is_staff=True,
                                                municipio=self.zacatlan, rol=Usuario.Rol.AUTORIDAD)
        autoridad.groups.add(Group.objects.get(name="Autoridad Municipal"))
        entrar_con_segundo_factor(self.client, autoridad)
        sin_filtro = lambda self, request: Tramite.objects.all()  # noqa: E731 - simula el error
        with mock.patch.object(TramiteAdmin, "get_queryset", sin_filtro):
            lista = self.client.get(reverse("admin:catalogo_tramite_changelist"))
            self.assertEqual(lista.context["cl"].result_count, 90)
            ajeno = self.client.get(reverse("admin:catalogo_tramite_change", args=[self.tramite_hua.pk]))
            self.assertNotEqual(ajeno.status_code, 200)
        # Después de la petición la conexión vuelve al alcance de plataforma.
        self.assertEqual(Tramite.objects.count(), 202)

    def test_el_catalogo_publico_no_se_restringe_al_personal(self):
        autoridad = Usuario.objects.create_user("autoridad.zac", password="Clave-larga-de-prueba-1", is_staff=True,
                                                municipio=self.zacatlan)
        entrar_con_segundo_factor(self.client, autoridad)
        self.assertEqual(self.client.get(reverse("catalogo:catalogo", args=["huauchinango"])).status_code, 200)

    def test_el_rol_de_la_aplicacion_no_se_salta_la_seguridad(self):
        self.assertEqual(checks.rol_sin_privilegios(None), [])
