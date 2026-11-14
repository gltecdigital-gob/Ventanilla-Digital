from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .bitacora import registrar
from .models import EventoBitacora


@receiver(user_logged_in)
def anotar_acceso(sender, request, user, **kwargs):
    registrar(EventoBitacora.Accion.ACCESO, f"Inicio de sesión de {user.get_username()}", request=request, usuario=user)


@receiver(user_login_failed)
def anotar_acceso_fallido(sender, credentials, request=None, **kwargs):
    nombre = str(credentials.get("username", ""))[:60]
    registrar(EventoBitacora.Accion.ACCESO_FALLIDO, f"Intento fallido con el usuario «{nombre}»", request=request)
