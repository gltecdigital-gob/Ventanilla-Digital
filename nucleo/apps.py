from django.apps import AppConfig


class NucleoConfig(AppConfig):
    name = "nucleo"
    verbose_name = "Municipios y bitácora"

    def ready(self):
        from . import senales  # noqa: F401
