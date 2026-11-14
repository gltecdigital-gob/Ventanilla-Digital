from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .segundo_factor import confirmado_de, sesion_verificada

PROTEGIDAS = ("/panel/", "/ventanilla/")
EXENTAS = ("/panel/segundo-factor/", "/panel/login/", "/panel/logout/", "/panel/jsi18n/")


class SegundoFactorMiddleware:
    """El personal no entra al panel ni a la ventanilla sin su segundo factor."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, "SEGUNDO_FACTOR_OBLIGATORIO", True)
            and request.path.startswith(PROTEGIDAS)
            and not request.path.startswith(EXENTAS)
            and request.user.is_authenticated
            and request.user.is_staff
            and not sesion_verificada(request)
        ):
            destino = "segundo_factor:verificar" if confirmado_de(request.user) else "segundo_factor:configurar"
            return redirect(f"{reverse(destino)}?next={quote(request.get_full_path())}")
        return self.get_response(request)
