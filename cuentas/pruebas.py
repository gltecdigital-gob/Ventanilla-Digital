"""Ayudas para pruebas: entrar como servidor público con el segundo factor ya cumplido."""
from django.utils import timezone

from . import segundo_factor as sf
from . import totp


def entrar_con_segundo_factor(client, usuario):
    client.force_login(usuario)
    factor = sf.pendiente_o_nuevo(usuario)
    factor.confirmado = timezone.now()
    factor.save(update_fields=["confirmado"])
    sesion = client.session
    sesion[sf.SESION] = sf.marca_de_sesion(usuario, factor)
    sesion.save()
    return factor


def codigo_vigente(factor):
    return totp.codigo(factor.secreto, totp.paso_actual())
