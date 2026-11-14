from django.apps import AppConfig


class CuentasConfig(AppConfig):
    name = "cuentas"
    verbose_name = "Servidores públicos"

    def ready(self):
        from . import senales  # noqa: F401
