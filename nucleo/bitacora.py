"""Funciones para escribir en la bitácora desde cualquier parte del sistema."""
from django.conf import settings

from .models import EventoBitacora


def ip_de(request):
    """IP de quien hace la petición.

    X-Forwarded-For solo se usa si CONFIAR_PROXY está activo: sin un proxy de confianza
    delante, cualquiera puede escribir ese encabezado y falsear su IP.
    """
    if request is None:
        return None
    ip = request.META.get("REMOTE_ADDR")
    if getattr(settings, "CONFIAR_PROXY", False):
        reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if reenviada:
            ip = reenviada.split(",")[-1].strip()
    return ip or None


def registrar(accion, descripcion, *, request=None, usuario=None, municipio=None, objeto=None, cambios=None,
              persona=None):
    if usuario is None and request is not None and getattr(request, "user", None) is not None:
        usuario = request.user if request.user.is_authenticated else None
    if municipio is None and objeto is not None:
        municipio = getattr(objeto, "municipio", None)
    if municipio is None and usuario is not None:
        municipio = getattr(usuario, "municipio", None)
    return EventoBitacora.objects.create(
        accion=accion,
        descripcion=descripcion[:300],
        usuario=usuario,
        persona=persona,
        municipio=municipio,
        modelo=objeto._meta.label if objeto is not None else "",
        objeto_id=str(objeto.pk) if objeto is not None and objeto.pk is not None else "",
        cambios=cambios or {},
        ip=ip_de(request),
    )
