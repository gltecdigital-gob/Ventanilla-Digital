"""Adaptador de inicio de sesión con Llave MX.

La plataforma pide la autenticación a Llave MX, recibe un código de un solo uso y lo
canjea por la identidad (CURP y nivel). Se selecciona con LLAVE_MX_BACKEND:

- "simulador": página de prueba que imita a Llave MX, solo en desarrollo.
- "atdt": integración real. Se completa con el manual técnico que entregue la ATDT al
  aprobar la solicitud de integración (protocolo, direcciones y datos que devuelve).
"""
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from .models import NivelConfianza


class LlaveMXNoDisponible(Exception):
    pass


@dataclass(frozen=True)
class IdentidadLlaveMX:
    curp: str
    sujeto: str
    verificada: bool

    @property
    def nivel(self):
        # Llave MX Básica equivale a nivel 2; Llave MX Verificada a nivel 3.
        return NivelConfianza.ALTO if self.verificada else NivelConfianza.VERIFICADO


def _backend():
    return getattr(settings, "LLAVE_MX_BACKEND", "simulador")


def url_autorizacion(request, estado):
    retorno = request.build_absolute_uri(reverse("ciudadania:llave_mx_retorno"))
    if _backend() == "simulador":
        return reverse("simuladores:llave_mx_autorizar") + "?" + urlencode({"state": estado, "redirect_uri": retorno})
    raise LlaveMXNoDisponible("La integración con Llave MX está pendiente del manual técnico de la ATDT.")


def canjear_codigo(codigo):
    if _backend() == "simulador":
        from simuladores import llave_mx

        datos = llave_mx.canjear(codigo)
        if datos is None:
            return None
        return IdentidadLlaveMX(curp=datos["curp"], sujeto=datos["sujeto"], verificada=datos["verificada"])
    raise LlaveMXNoDisponible("La integración con Llave MX está pendiente del manual técnico de la ATDT.")
