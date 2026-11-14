"""Carga los municipios del piloto, sus dependencias y su inventario de trámites.

Se puede ejecutar varias veces: no duplica ni pisa fichas que ya fueron editadas.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from catalogo.models import Tramite
from nucleo.models import Dependencia, Municipio

MUNICIPIOS = [
    {
        "slug": "zacatlan", "nombre": "Zacatlán", "archivo": "zacatlan.txt",
        "telefono": "797 124 57 71", "correo": "presidenciamunicipal@zacatlan.gob.mx",
        "direccion": "Palacio Municipal s/n, Col. Centro, C.P. 73310",
    },
    {
        "slug": "huauchinango", "nombre": "Huauchinango", "archivo": "huauchinango.txt",
        "telefono": "776 762 0699", "correo": "presidencia@huauchinango.gob.mx",
        "direccion": "Plaza de la Constitución s/n, Col. Centro",
    },
]

# Trámites que ya se pagan o consultan en un portal existente.
CANAL_POR_RUTA = {"A": Tramite.Canal.MIXTO}

GRUPOS = {
    "Autoridad Municipal": [
        "catalogo.add_tramite", "catalogo.change_tramite", "catalogo.delete_tramite", "catalogo.view_tramite",
        "catalogo.add_requisito", "catalogo.change_requisito", "catalogo.delete_requisito", "catalogo.view_requisito",
        "nucleo.add_dependencia", "nucleo.change_dependencia", "nucleo.view_dependencia",
        "nucleo.change_municipio", "nucleo.view_municipio", "nucleo.view_eventobitacora",
        "cuentas.add_usuario", "cuentas.change_usuario", "cuentas.view_usuario",
        "ciudadania.verificar_identidad",
    ],
    "Ventanilla": ["ciudadania.verificar_identidad", "catalogo.view_tramite"],
    "Enlace de dependencia": [
        "catalogo.change_tramite", "catalogo.view_tramite",
        "catalogo.add_requisito", "catalogo.change_requisito", "catalogo.delete_requisito", "catalogo.view_requisito",
        "nucleo.view_dependencia",
    ],
    "Solo consulta": ["catalogo.view_tramite", "catalogo.view_requisito", "nucleo.view_dependencia"],
}


def leer(archivo):
    for linea in Path(settings.BASE_DIR, "datos", archivo).read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        clave, dependencia, nombre, ruta = (parte.strip() for parte in linea.split("|"))
        yield clave, dependencia, nombre, ruta


class Command(BaseCommand):
    help = "Carga Zacatlán y Huauchinango con su inventario de trámites clasificado por ruta."

    @transaction.atomic
    def handle(self, *args, **opciones):
        self._grupos()
        for datos in MUNICIPIOS:
            municipio, _ = Municipio.objects.update_or_create(
                slug=datos["slug"],
                defaults={k: datos[k] for k in ("nombre", "telefono", "correo", "direccion")},
            )
            nuevos = 0
            for clave, nombre_dependencia, nombre, ruta in leer(datos["archivo"]):
                dependencia, _ = Dependencia.objects.get_or_create(municipio=municipio, nombre=nombre_dependencia)
                es_servicio = clave.startswith("S") or nombre.lower().startswith("reporte")
                _, creado = Tramite.objects.get_or_create(
                    municipio=municipio,
                    clave=clave,
                    defaults={
                        "nombre": nombre,
                        "dependencia": dependencia,
                        "ruta": ruta,
                        "tipo": Tramite.Tipo.SERVICIO if es_servicio else Tramite.Tipo.TRAMITE,
                        "canal": CANAL_POR_RUTA.get(ruta, Tramite.Canal.PRESENCIAL),
                    },
                )
                nuevos += creado
            total = Tramite.objects.filter(municipio=municipio).count()
            if opciones["verbosity"] > 0:
                self.stdout.write(self.style.SUCCESS(f"{municipio.nombre}: {nuevos} trámites nuevos, {total} en total."))

    def _grupos(self):
        for nombre, permisos in GRUPOS.items():
            grupo, _ = Group.objects.get_or_create(name=nombre)
            objetos = []
            for permiso in permisos:
                app, codigo = permiso.split(".")
                objetos.append(Permission.objects.get(content_type__app_label=app, codename=codigo))
            grupo.permissions.set(objetos)
