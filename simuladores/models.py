from django.db import models


class MensajeSimulado(models.Model):
    """Buzón de pruebas: correos y mensajes que en producción saldrían al proveedor real."""

    class Canal(models.TextChoices):
        CORREO = "correo", "Correo"
        SMS = "sms", "Mensaje de texto"

    canal = models.CharField(max_length=10, choices=Canal.choices)
    destino = models.CharField(max_length=254)
    asunto = models.CharField(max_length=200, blank=True)
    texto = models.TextField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado", "-id"]
        verbose_name = "mensaje simulado"
        verbose_name_plural = "buzón de pruebas"
