import segno
from django import forms
from django.contrib import admin
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe

from ciudadania import seguridad
from nucleo.bitacora import registrar
from nucleo.models import EventoBitacora

from . import segundo_factor as sf
from . import totp

EMISOR = "Tramites municipales"


class CodigoForm(forms.Form):
    codigo = forms.CharField(
        label="Código", max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "autofocus": True, "spellcheck": "false"}),
    )


def _siguiente(request):
    destino = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return destino
    return "/panel/"


def solo_personal(vista):
    @login_required(login_url="admin:login")
    def envoltura(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("admin:login")
        return vista(request, *args, **kwargs)

    return envoltura


def _pagina(request, plantilla, contexto):
    """Las páginas del segundo factor usan el encabezado y estilo del panel."""
    base = admin.site.each_context(request)
    # Sin menú lateral: antes de verificar el segundo factor no se muestra el contenido del panel.
    base.update({"is_nav_sidebar_enabled": False, "available_apps": []})
    return render(request, plantilla, {**base, **contexto})


def _bloqueado(usuario):
    return seguridad.excede_limite("segundo_factor_usuario", str(usuario.pk))


def _fallido(request):
    seguridad.anotar_intento("segundo_factor_usuario", str(request.user.pk))
    registrar(EventoBitacora.Accion.SEGUNDO_FACTOR_FALLIDO, f"Código de segundo factor incorrecto de {request.user.get_username()}",
              request=request)


@solo_personal
def configurar(request):
    if sf.confirmado_de(request.user):
        return redirect(f"{request.path.replace('configurar', 'verificar')}?next={_siguiente(request)}")
    factor = sf.pendiente_o_nuevo(request.user)
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _bloqueado(request.user):
            form.add_error(None, "Demasiados intentos. Espera 15 minutos.")
        else:
            paso = totp.verificar(factor.secreto, form.cleaned_data["codigo"])
            if paso is None:
                _fallido(request)
                form.add_error("codigo", "El código no es correcto. Revisa que la hora de tu teléfono sea automática.")
            else:
                factor.ultimo_paso = paso
                factor.confirmado = timezone.now()
                factor.save(update_fields=["ultimo_paso", "confirmado"])
                codigos = sf.generar_codigos_respaldo(request.user)
                sf.marcar_sesion(request, factor)
                registrar(EventoBitacora.Accion.SEGUNDO_FACTOR, f"Segundo factor activado por {request.user.get_username()}",
                          request=request)
                return _pagina(request, "segundo_factor/respaldo.html", {"codigos": codigos, "siguiente": _siguiente(request),
                                                                        "title": "Guarda tus códigos de respaldo"})
    uri = totp.uri_aprovisionamiento(factor.secreto, request.user.get_username(), EMISOR)
    secreto = factor.secreto
    return _pagina(request, "segundo_factor/configurar.html", {
        "form": form,
        "qr": mark_safe(segno.make(uri, error="m").svg_inline(scale=5, dark="#1c2421", light="#ffffff")),
        "secreto_agrupado": " ".join(secreto[i:i + 4] for i in range(0, len(secreto), 4)),
        "siguiente": _siguiente(request),
        "title": "Activa tu segundo factor",
    })


@solo_personal
def verificar(request):
    factor = sf.confirmado_de(request.user)
    if factor is None:
        return redirect(f"{request.path.replace('verificar', 'configurar')}?next={_siguiente(request)}")
    if sf.sesion_verificada(request):
        return redirect(_siguiente(request))
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _bloqueado(request.user):
            form.add_error(None, "Demasiados intentos. Espera 15 minutos o pide a la Autoridad Municipal que reinicie tu segundo factor.")
        else:
            correcto, fue_respaldo = sf.verificar(request.user, factor, form.cleaned_data["codigo"])
            if correcto:
                sf.marcar_sesion(request, factor)
                detalle = " con código de respaldo" if fue_respaldo else ""
                registrar(EventoBitacora.Accion.SEGUNDO_FACTOR, f"Segundo factor verificado{detalle} por {request.user.get_username()}",
                          request=request)
                return redirect(_siguiente(request))
            _fallido(request)
            form.add_error("codigo", "El código no es correcto o ya se usó.")
    restantes = request.user.codigos_respaldo.filter(usado__isnull=True).count()
    return _pagina(request, "segundo_factor/verificar.html", {
        "form": form, "siguiente": _siguiente(request), "restantes": restantes, "title": "Verificación en dos pasos",
    })


@solo_personal
def salir(request):
    if request.method == "POST":
        logout(request)
    return redirect("admin:login")
