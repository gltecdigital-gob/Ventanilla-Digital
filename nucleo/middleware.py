from django.conf import settings

from . import alcance

# Rutas donde trabaja el personal municipal. Fuera de ellas (catálogo público, cuenta
# ciudadana) el alcance es de plataforma y cada vista filtra por municipio o por persona.
RUTAS_DEL_PERSONAL = ("/panel/", "/ventanilla/")


class AlcanceMunicipalMiddleware:
    """Restringe en la base de datos lo que el personal municipal puede leer y escribir.

    Va después de AuthenticationMiddleware. La tabla de usuarios no tiene seguridad
    por fila, así que identificar al usuario no depende del alcance.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        restringido = (
            request.path.startswith(RUTAS_DEL_PERSONAL)
            and usuario is not None
            and usuario.is_authenticated
            and not usuario.is_superuser
        )
        if restringido:
            alcance.fijar(alcance.MUNICIPIO, usuario.municipio_id)
        else:
            alcance.fijar(alcance.PLATAFORMA)
        try:
            return self.get_response(request)
        finally:
            # La conexión se reutiliza entre peticiones: se deja en el estado inicial.
            alcance.fijar(alcance.PLATAFORMA)
