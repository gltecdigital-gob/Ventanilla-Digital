"""Envío de códigos y avisos por correo o mensaje de texto.

Correo: el backend de correo de Django (EMAIL_BACKEND).
Mensajes de texto: SMS_BACKEND. "simulador" los guarda en el buzón de pruebas;
para producción se conecta un proveedor de mensajería contratado por el municipio.
"""
from django.conf import settings
from django.core.mail import send_mail


class EnvioNoDisponible(Exception):
    pass


def enviar(destino, asunto, texto):
    if "@" in destino:
        send_mail(asunto, texto, None, [destino], fail_silently=False)
        return
    backend = getattr(settings, "SMS_BACKEND", "simulador")
    if backend == "simulador":
        from simuladores.models import MensajeSimulado

        MensajeSimulado.objects.create(canal=MensajeSimulado.Canal.SMS, destino=destino, asunto=asunto, texto=texto)
        return
    raise EnvioNoDisponible("No hay proveedor de mensajes de texto configurado.")


def enviar_codigo(destino, codigo):
    enviar(
        destino,
        "Tu código de acceso",
        f"Tu código es {codigo}. Vence en 10 minutos. Nadie del ayuntamiento te lo pedirá; no lo compartas.",
    )


def avisar_al_titular(persona, texto):
    """Aviso de seguridad cuando se usa la CURP de una persona."""
    if persona.destino_codigo:
        enviar(persona.destino_codigo, "Aviso de seguridad de tu cuenta", texto)
