"""Identidad de la ciudadanía.

Una persona tiene un solo perfil en toda la plataforma, identificado por su CURP
(art. 59 LNETB). Las cuentas de la ciudadanía viven aparte de las de los
servidores públicos (cuentas.Usuario).
"""
from django.conf import settings
from django.db import models

from nucleo.models import Municipio


class NivelConfianza(models.IntegerChoices):
    BASICO = 1, "1. Básico"
    VERIFICADO = 2, "2. Verificado"
    ALTO = 3, "3. Alto"


class Persona(models.Model):
    curp = models.CharField("CURP", max_length=18, unique=True)
    # Datos oficiales devueltos por RENAPO. La persona no puede editarlos.
    nombres = models.CharField(max_length=120)
    primer_apellido = models.CharField(max_length=80)
    segundo_apellido = models.CharField(max_length=80, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=1, blank=True)
    entidad_nacimiento = models.CharField(max_length=2, blank=True)
    renapo_validado = models.DateTimeField("validada en RENAPO", null=True, blank=True)
    renapo_simulado = models.BooleanField(
        "validada con el simulador", default=False,
        help_text="Verdadero si la validación vino del simulador y no del servicio real de RENAPO.",
    )
    # Medios de contacto
    correo = models.EmailField(blank=True)
    telefono = models.CharField("teléfono celular", max_length=10, blank=True)
    contacto_confirmado = models.BooleanField(default=False)
    # Confianza: el nivel más alto que la persona ha comprobado.
    nivel_confianza = models.PositiveSmallIntegerField(choices=NivelConfianza.choices, default=NivelConfianza.BASICO)
    acepto_aviso = models.DateTimeField("aceptó el aviso de privacidad", null=True, blank=True)
    activa = models.BooleanField(default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["primer_apellido", "segundo_apellido", "nombres"]
        verbose_name = "persona"
        verbose_name_plural = "personas"
        permissions = [("verificar_identidad", "Puede registrar y verificar identidad en ventanilla")]

    def __str__(self):
        return f"{self.nombre_completo} ({self.curp})"

    @property
    def nombre_completo(self):
        return " ".join(p for p in (self.nombres, self.primer_apellido, self.segundo_apellido) if p)

    @property
    def destino_codigo(self):
        """Medio confirmado al que se envían los códigos de acceso."""
        if not self.contacto_confirmado:
            return ""
        return self.correo or self.telefono

    def subir_nivel(self, nivel):
        if nivel > self.nivel_confianza:
            self.nivel_confianza = nivel
            self.save(update_fields=["nivel_confianza"])


class IdentidadVinculada(models.Model):
    class Proveedor(models.TextChoices):
        CUENTA_MUNICIPAL = "cuenta_municipal", "Cuenta municipal"
        LLAVE_MX = "llave_mx", "Llave MX"

    persona = models.ForeignKey(Persona, related_name="identidades", on_delete=models.CASCADE)
    proveedor = models.CharField(max_length=20, choices=Proveedor.choices)
    sujeto = models.CharField(max_length=120, help_text="Identificador de la persona en el proveedor")
    nivel = models.PositiveSmallIntegerField(choices=NivelConfianza.choices)
    vinculada = models.DateTimeField(auto_now_add=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "identidad vinculada"
        verbose_name_plural = "identidades vinculadas"
        constraints = [
            models.UniqueConstraint(fields=["proveedor", "sujeto"], name="sujeto_unico_por_proveedor"),
            models.UniqueConstraint(fields=["persona", "proveedor"], name="un_proveedor_por_persona"),
        ]

    def __str__(self):
        return f"{self.get_proveedor_display()} · {self.persona.curp}"


class VerificacionPresencial(models.Model):
    """Constancia de que un servidor público comprobó en persona la identidad."""

    class TipoIdentificacion(models.TextChoices):
        INE = "ine", "Credencial para votar"
        PASAPORTE = "pasaporte", "Pasaporte"
        CEDULA = "cedula", "Cédula profesional"
        LICENCIA = "licencia", "Licencia de conducir"
        CURP_BIOMETRICA = "curp_biometrica", "CURP biométrica"
        INAPAM = "inapam", "Credencial INAPAM"
        OTRA = "otra", "Otra identificación oficial con fotografía"

    persona = models.ForeignKey(Persona, related_name="verificaciones", on_delete=models.CASCADE)
    servidor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT)
    tipo_identificacion = models.CharField("identificación presentada", max_length=20, choices=TipoIdentificacion.choices)
    ultimos_digitos = models.CharField(
        "últimos 4 caracteres del documento", max_length=4,
        help_text="Solo los últimos 4: no se guarda el número completo (datos mínimos).",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "verificación presencial"
        verbose_name_plural = "verificaciones presenciales"


class CodigoUnUso(models.Model):
    """Código de 6 dígitos enviado al correo o teléfono. Solo se guarda su huella."""

    class Proposito(models.TextChoices):
        REGISTRO = "registro", "Confirmar contacto en el registro"
        ACCESO = "acceso", "Iniciar sesión"

    curp = models.CharField(max_length=18, db_index=True)
    proposito = models.CharField(max_length=10, choices=Proposito.choices)
    destino = models.CharField(max_length=254)
    huella = models.CharField(max_length=64)
    expira = models.DateTimeField()
    intentos = models.PositiveSmallIntegerField(default=0)
    usado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]


class RegistroIntento(models.Model):
    """Intentos recientes para limitar abusos (por CURP y por dirección IP)."""

    tipo = models.CharField(max_length=30)
    clave = models.CharField(max_length=64, help_text="Huella de la CURP o de la IP; no se guarda el dato en claro")
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["tipo", "clave", "creado"])]
