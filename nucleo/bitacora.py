"""Funciones para escribir en la bitácora desde cualquier parte del sistema."""
from .models import EventoBitacora


def ip_de(request):
    if request is None:
        return None
    # Detrás de un proxy de confianza la IP real llega en X-Forwarded-For.
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = reenviada.split(",")[0].strip() if reenviada else request.META.get("REMOTE_ADDR")
    return ip or None


def registrar(accion, descripcion, *, request=None, usuario=None, municipio=None, objeto=None, cambios=None):
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
        municipio=municipio,
        modelo=objeto._meta.label if objeto is not None else "",
        objeto_id=str(objeto.pk) if objeto is not None and objeto.pk is not None else "",
        cambios=cambios or {},
        ip=ip_de(request),
    )
