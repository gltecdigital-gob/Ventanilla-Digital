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
