from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import connection


@register()
def middleware_de_alcance(app_configs, **kwargs):
    nombre = "nucleo.middleware.AlcanceMunicipalMiddleware"
    errores = []
    if nombre not in settings.MIDDLEWARE:
        errores.append(Error(f"Falta {nombre} en MIDDLEWARE: sin él no se aplica la seguridad por fila.", id="nucleo.E001"))
    elif settings.MIDDLEWARE.index(nombre) < settings.MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware"):
        errores.append(Error(f"{nombre} debe ir después de AuthenticationMiddleware.", id="nucleo.E002"))
    return errores


@register(Tags.database, deploy=True)
def rol_sin_privilegios(app_configs, databases=None, **kwargs):
    """Un superusuario o un rol con BYPASSRLS se salta la seguridad por fila."""
    if connection.vendor != "postgresql":
        return []
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        superusuario, salta_rls = cursor.fetchone()
    if superusuario or salta_rls:
        return [Error(
            "La aplicación se conecta a PostgreSQL con un rol que se salta la seguridad por fila "
            "(superusuario o BYPASSRLS). Usa un rol sin esos privilegios.",
            id="nucleo.E003",
        )]
    return []
