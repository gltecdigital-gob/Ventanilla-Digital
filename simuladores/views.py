from functools import wraps
from urllib.parse import urlencode, urlsplit

from django import forms
from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render

from . import llave_mx
from .curp import normalizar, validar_formato
from .models import MensajeSimulado


def solo_simulacion(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not (settings.DEBUG or getattr(settings, "PERMITIR_SIMULADORES", False)):
            raise Http404
        return vista(request, *args, **kwargs)

    return envoltura


class AutorizarForm(forms.Form):
    curp = forms.CharField(label="CURP", max_length=24)
    verificada = forms.BooleanField(label="Simular Llave MX Verificada (nivel 3)", required=False)

    def clean_curp(self):
        curp = normalizar(self.cleaned_data["curp"])
        valida, motivo = validar_formato(curp)
        if not valida:
            raise forms.ValidationError(motivo)
        return curp


@solo_simulacion
def llave_mx_autorizar(request):
    estado = request.GET.get("state", "")
    retorno = request.GET.get("redirect_uri", "")
    # Solo se regresa a esta misma plataforma.
    if urlsplit(retorno).netloc != request.get_host():
        raise Http404
    form = AutorizarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        codigo = llave_mx.emitir(form.cleaned_data["curp"], form.cleaned_data["verificada"])
        return redirect(f"{retorno}?{urlencode({'code': codigo, 'state': estado})}")
    return render(request, "simuladores/llave_mx.html", {"form": form})


@solo_simulacion
def buzon(request):
    return render(request, "simuladores/buzon.html", {"mensajes": MensajeSimulado.objects.all()[:30]})
