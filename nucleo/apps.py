from django.apps import AppConfig


class NucleoConfig(AppConfig):
    name = "nucleo"
    verbose_name = "Municipios y bitácora"

    def ready(self):
        from django.db.backends.signals import connection_created

        from . import checks, senales  # noqa: F401
        from .alcance import al_crear_conexion

        connection_created.connect(al_crear_conexion, dispatch_uid="nucleo_alcance_inicial")
