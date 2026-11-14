"""Sesión de la ciudadanía, separada de la de los servidores públicos."""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from nucleo.bitacora import registrar
from nucleo.models import EventoBitacora

from .models import IdentidadVinculada, Persona

CLAVE = "ciudadano"
DURACION_SEGUNDOS = 30 * 60  # se renueva con cada visita


def iniciar(request, persona, proveedor, nivel):
    request.session.cycle_key()  # evita fijación de sesión
    request.session[CLAVE] = {"id": persona.pk, "via": proveedor, "nivel": int(nivel)}
    request.session.set_expiry(DURACION_SEGUNDOS)
    IdentidadVinculada.objects.filter(persona=persona, proveedor=proveedor).update(ultimo_uso=timezone.now())
    registrar(
        EventoBitacora.Accion.ACCESO_CIUDADANO,
        f"Inicio de sesión ciudadano por {IdentidadVinculada.Proveedor(proveedor).label}",
        request=request, persona=persona, cambios={"nivel": int(nivel)},
    )


def cerrar(request):
    request.session.pop(CLAVE, None)
    request.session.cycle_key()


def datos(request):
    return request.session.get(CLAVE) or {}


def persona_actual(request):
    if not hasattr(request, "_persona_en_sesion"):
        identificador = datos(request).get("id")
        request._persona_en_sesion = (
            Persona.objects.filter(pk=identificador, activa=True).first() if identificador else None
        )
    return request._persona_en_sesion


def nivel_sesion(request):
    return datos(request).get("nivel", 0) if persona_actual(request) else 0


def requiere_persona(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if persona_actual(request) is None:
            cerrar(request)
            messages.info(request, "Inicia sesión para continuar.")
            return redirect("ciudadania:entrar")
        request.session.set_expiry(DURACION_SEGUNDOS)
        return vista(request, *args, **kwargs)

    return envoltura


def requiere_nivel(nivel):
    """Para las vistas de trámites (etapa 3): exige un nivel de confianza mínimo en la sesión."""

    def decorador(vista):
        @requiere_persona
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if nivel_sesion(request) < nivel:
                messages.warning(request, "Este trámite requiere un nivel de confianza mayor. Abajo te decimos cómo subirlo.")
                return redirect("ciudadania:perfil")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
