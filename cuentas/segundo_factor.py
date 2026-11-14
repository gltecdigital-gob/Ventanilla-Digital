"""Reglas del segundo factor para servidores públicos."""
import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import totp
from .models import CodigoRespaldo, SegundoFactor

SESION = "segundo_factor_ok"
CANTIDAD_RESPALDO = 10
ALFABETO_RESPALDO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para evitar confusiones


def _huella(codigo):
    return hmac.new(settings.SECRET_KEY.encode(), ("respaldo:" + codigo).encode(), hashlib.sha256).hexdigest()


def _normalizar_respaldo(codigo):
    return "".join(c for c in (codigo or "").upper() if c.isalnum())


def confirmado_de(usuario):
    return SegundoFactor.objects.filter(usuario=usuario, confirmado__isnull=False).first()


def marca_de_sesion(usuario, factor):
    return f"{usuario.pk}:{factor.pk}"


def sesion_verificada(request):
    """La sesión pasó el segundo factor del dispositivo vigente del usuario."""
    marca = request.session.get(SESION)
    if not marca:
        return False
    factor = confirmado_de(request.user)
    return factor is not None and marca == marca_de_sesion(request.user, factor)


def marcar_sesion(request, factor):
    request.session.cycle_key()
    request.session[SESION] = marca_de_sesion(request.user, factor)


def pendiente_o_nuevo(usuario):
    """Factor aún no confirmado del usuario; lo crea si no existe."""
    factor, creado = SegundoFactor.objects.get_or_create(usuario=usuario, defaults={"secreto_cifrado": ""})
    if creado or not factor.secreto_cifrado:
        factor.secreto = totp.generar_secreto()
        factor.save(update_fields=["secreto_cifrado"])
    return factor


@transaction.atomic
def generar_codigos_respaldo(usuario):
    CodigoRespaldo.objects.filter(usuario=usuario).delete()
    codigos = []
    for _ in range(CANTIDAD_RESPALDO):
        crudo = "".join(secrets.choice(ALFABETO_RESPALDO) for _ in range(10))
        codigos.append(f"{crudo[:5]}-{crudo[5:]}")
        CodigoRespaldo.objects.create(usuario=usuario, huella=_huella(crudo))
    return codigos


def verificar(usuario, factor, propuesto):
    """Acepta un código de la aplicación o uno de respaldo. Devuelve (correcto, fue_respaldo)."""
    with transaction.atomic():
        factor = SegundoFactor.objects.select_for_update().get(pk=factor.pk)
        paso = totp.verificar(factor.secreto, propuesto, ultimo_paso_usado=factor.ultimo_paso)
        if paso is not None:
            factor.ultimo_paso = paso
            factor.save(update_fields=["ultimo_paso"])
            return True, False
    normalizado = _normalizar_respaldo(propuesto)
    if len(normalizado) == 10:
        usados = CodigoRespaldo.objects.filter(usuario=usuario, huella=_huella(normalizado), usado__isnull=True).update(usado=timezone.now())
        if usados:
            return True, True
    return False, False


def reiniciar(usuario):
    SegundoFactor.objects.filter(usuario=usuario).delete()
    CodigoRespaldo.objects.filter(usuario=usuario).delete()
