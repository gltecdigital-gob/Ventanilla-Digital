from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .segundo_factor import SESION


@receiver(user_logged_in)
def exigir_segundo_factor_en_cada_acceso(sender, request, user, **kwargs):
    request.session.pop(SESION, None)
