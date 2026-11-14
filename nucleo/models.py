from django.conf import settings
from django.db import models


class Municipio(models.Model):
    """Cada ayuntamiento que usa la plataforma. Es la unidad de separación de datos."""

    nombre = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, help_text="Parte de la dirección web, por ejemplo: zacatlan")
    estado = models.CharField(max_length=60, default="Puebla")
    telefono = models.CharField("teléfono", max_length=40, blank=True)
    correo = models.EmailField(blank=True)
    direccion = models.CharField("dirección", max_length=200, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ModeloMunicipal(models.Model):
    """Base de todo registro que pertenece a un municipio.

    La separación entre municipios se aplica en las consultas del panel y de las
    páginas públicas. En PostgreSQL se reforzará con seguridad por fila (etapa 2).
    """

    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class Dependencia(ModeloMunicipal):
    nombre = models.CharField(max_length=160)
    siglas = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["municipio", "nombre"], name="dependencia_unica_por_municipio"),
        ]

    def __str__(self):
        return self.nombre


class EventoBitacora(models.Model):
    """Registro inalterable de lo que ocurre en la plataforma: solo se agrega."""

    class Accion(models.TextChoices):
        CREAR = "crear", "Crear"
        MODIFICAR = "modificar", "Modificar"
        ELIMINAR = "eliminar", "Eliminar"
        PUBLICAR = "publicar", "Publicar"
        ACCESO = "acceso", "Inicio de sesión"
        ACCESO_FALLIDO = "acceso_fallido", "Intento de acceso fallido"

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    municipio = models.ForeignKey(Municipio, null=True, blank=True, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    accion = models.CharField("acción", max_length=20, choices=Accion.choices)
    modelo = models.CharField(max_length=80, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    descripcion = models.CharField("descripción", max_length=300)
    cambios = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "evento de bitácora"
        verbose_name_plural = "bitácora"

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} · {self.get_accion_display()} · {self.descripcion}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("La bitácora no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("La bitácora no se puede borrar.")
