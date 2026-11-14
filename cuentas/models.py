from django.contrib.auth.models import AbstractUser
from django.db import models

from nucleo.models import Dependencia, Municipio


class Usuario(AbstractUser):
    """Cuenta de una persona servidora pública que usa el panel.

    Las cuentas de la ciudadanía (Llave MX y cuenta municipal) se agregan en la etapa 2
    y viven aparte de estas.
    """

    class Rol(models.TextChoices):
        AUTORIDAD = "autoridad", "Autoridad Municipal de Simplificación y Digitalización"
        ENLACE = "enlace", "Enlace de dependencia"
        VENTANILLA = "ventanilla", "Personal de ventanilla"
        CONSULTA = "consulta", "Solo consulta"

    municipio = models.ForeignKey(Municipio, null=True, blank=True, on_delete=models.PROTECT)
    dependencia = models.ForeignKey(Dependencia, null=True, blank=True, on_delete=models.PROTECT)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CONSULTA)

    class Meta:
        verbose_name = "servidor público"
        verbose_name_plural = "servidores públicos"

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        if self.dependencia and self.municipio and self.dependencia.municipio_id != self.municipio_id:
            raise ValidationError({"dependencia": "La dependencia no pertenece al municipio elegido."})
        if self.rol == self.Rol.ENLACE and not self.dependencia:
            raise ValidationError({"dependencia": "Un Enlace debe tener dependencia."})


class SegundoFactor(models.Model):
    """Aplicación de autenticación vinculada a la cuenta de un servidor público."""

    usuario = models.OneToOneField(Usuario, related_name="segundo_factor", on_delete=models.CASCADE)
    secreto_cifrado = models.TextField()
    confirmado = models.DateTimeField(null=True, blank=True)
    ultimo_paso = models.BigIntegerField(default=0, help_text="Último periodo de 30 s aceptado; evita reutilizar un código")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "segundo factor"
        verbose_name_plural = "segundos factores"

    @property
    def secreto(self):
        from .cifrado import descifrar

        return descifrar(self.secreto_cifrado)

    @secreto.setter
    def secreto(self, valor):
        from .cifrado import cifrar

        self.secreto_cifrado = cifrar(valor)


class CodigoRespaldo(models.Model):
    """Códigos de un solo uso para entrar si se pierde el teléfono. Solo se guarda su huella."""

    usuario = models.ForeignKey(Usuario, related_name="codigos_respaldo", on_delete=models.CASCADE)
    huella = models.CharField(max_length=64)
    usado = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "código de respaldo"
        verbose_name_plural = "códigos de respaldo"
