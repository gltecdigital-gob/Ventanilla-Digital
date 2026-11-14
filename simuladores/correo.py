from django.core.mail.backends.base import BaseEmailBackend


class BuzonBackend(BaseEmailBackend):
    """Backend de correo para desarrollo: guarda cada correo en el buzón de pruebas."""

    def send_messages(self, email_messages):
        from .models import MensajeSimulado

        enviados = 0
        for mensaje in email_messages:
            for destino in mensaje.recipients():
                MensajeSimulado.objects.create(
                    canal=MensajeSimulado.Canal.CORREO, destino=destino, asunto=mensaje.subject, texto=mensaje.body,
                )
            enviados += 1
        return enviados
