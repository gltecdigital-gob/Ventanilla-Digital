from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from nucleo.models import Dependencia, ModeloMunicipal


class Tramite(ModeloMunicipal):
    """Ficha de un trámite o servicio.

    Reúne los datos que el artículo 54 de la Ley Nacional para Eliminar Trámites
    Burocráticos pide inscribir en el Portal Ciudadano Único, más los datos de
    gestión del proyecto (ruta de digitalización y estatus de la ficha).
    """

    class Tipo(models.TextChoices):
        TRAMITE = "tramite", "Trámite"
        SERVICIO = "servicio", "Servicio"

    class Canal(models.TextChoices):
        PRESENCIAL = "presencial", "Presencial"
        MIXTO = "mixto", "Presencial y en línea"
        EN_LINEA = "en_linea", "En línea"

    class Ficta(models.TextChoices):
        NO_APLICA = "no_aplica", "No aplica"
        AFIRMATIVA = "afirmativa", "Afirmativa ficta"
        NEGATIVA = "negativa", "Negativa ficta"

    class Ruta(models.TextChoices):
        A = "A", "A. Adoptar plataforma existente"
        B = "B", "B. Digitalizar ya"
        C = "C", "C. Simplificar y digitalizar"
        D = "D", "D. Rediseño profundo"
        E = "E", "E. Servicio presencial"

    class Estatus(models.TextChoices):
        INVENTARIADO = "inventariado", "Inventariado (ficha por levantar)"
        CAPTURADO = "capturado", "Capturado (en revisión)"
        PUBLICADO = "publicado", "Publicado"
        ARCHIVADO = "archivado", "Archivado"

    class Nivel(models.IntegerChoices):
        BASICO = 1, "1. Básico"
        VERIFICADO = 2, "2. Verificado"
        ALTO = 3, "3. Alto"

    # Identificación
    clave = models.CharField(max_length=40)
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.TRAMITE)
    dependencia = models.ForeignKey(Dependencia, on_delete=models.PROTECT)
    descripcion = models.TextField("descripción en lenguaje ciudadano", blank=True)
    modalidad = models.CharField(max_length=120, blank=True, help_text="Por ejemplo: persona física, persona moral, renovación")
    canal = models.CharField(max_length=12, choices=Canal.choices, default=Canal.PRESENCIAL)
    fundamento = models.TextField("fundamento jurídico", blank=True, help_text="Ordenamiento y artículos")

    # Resolución
    plazo_resolucion_dias = models.PositiveIntegerField("plazo de resolución (días hábiles)", null=True, blank=True)
    ficta = models.CharField("si no hay respuesta en plazo", max_length=12, choices=Ficta.choices, default=Ficta.NO_APLICA)
    plazo_prevencion_dias = models.PositiveIntegerField("plazo de prevención (días hábiles)", null=True, blank=True)
    inspeccion = models.TextField("inspección o verificación", blank=True, help_text="Objetivo y autoridad que la realiza; vacío si no aplica")
    vigencia = models.CharField("vigencia del documento que se obtiene", max_length=120, blank=True)

    # Costo
    costo = models.DecimalField("monto de derechos", max_digits=10, decimal_places=2, null=True, blank=True,
                                help_text="En pesos. Escribe 0 si es gratuito; deja vacío si aún no se levanta.")
    costo_detalle = models.CharField("detalle del costo", max_length=200, blank=True, help_text="Artículo de la ley de ingresos o cómo se calcula")
    formas_pago = models.CharField("formas de pago", max_length=200, blank=True)

    # Atención
    oficinas = models.TextField("oficinas donde se realiza", blank=True)
    horarios = models.CharField(max_length=200, blank=True)
    contacto = models.CharField("teléfono o correo de contacto", max_length=200, blank=True)

    # Gestión
    ruta = models.CharField("ruta de digitalización", max_length=1, choices=Ruta.choices, blank=True)
    nivel_confianza = models.PositiveSmallIntegerField("nivel de confianza requerido", choices=Nivel.choices, default=Nivel.BASICO)
    clave_catalogo_nacional = models.CharField("clave en el catálogo nacional homologado", max_length=60, blank=True)
    estatus = models.CharField(max_length=14, choices=Estatus.choices, default=Estatus.INVENTARIADO)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["dependencia__nombre", "nombre"]
        verbose_name = "trámite o servicio"
        verbose_name_plural = "trámites y servicios"
        constraints = [
            models.UniqueConstraint(fields=["municipio", "clave"], name="clave_unica_por_municipio"),
        ]

    def __str__(self):
        return f"{self.clave} · {self.nombre}"

    def get_absolute_url(self):
        return reverse("catalogo:ficha", args=[self.municipio.slug, self.clave])

    def faltantes_para_publicar(self):
        """Lo que le falta a la ficha para poder exigirse a la ciudadanía."""
        faltan = []
        if not self.descripcion.strip():
            faltan.append("descripción en lenguaje ciudadano")
        if not self.fundamento.strip():
            faltan.append("fundamento jurídico")
        if self.plazo_resolucion_dias is None:
            faltan.append("plazo de resolución")
        if self.costo is None:
            faltan.append("monto de derechos (0 si es gratuito)")
        if not self.oficinas.strip() and self.canal != self.Canal.EN_LINEA:
            faltan.append("oficinas donde se realiza")
        if not self.contacto.strip():
            faltan.append("contacto")
        return faltan

    def clean(self):
        super().clean()
        if self.dependencia_id and self.municipio_id and self.dependencia.municipio_id != self.municipio_id:
            raise ValidationError({"dependencia": "La dependencia no pertenece a este municipio."})
        if self.estatus == self.Estatus.PUBLICADO:
            faltan = self.faltantes_para_publicar()
            if faltan:
                raise ValidationError({"estatus": "No se puede publicar. Falta: " + "; ".join(faltan) + "."})

    @property
    def publicado(self):
        return self.estatus == self.Estatus.PUBLICADO

    @property
    def es_gratuito(self):
        return self.costo is not None and self.costo == 0


class Requisito(models.Model):
    class Formato(models.TextChoices):
        ORIGINAL = "original", "Original"
        COPIA_SIMPLE = "copia_simple", "Copia simple"
        COPIA_CERTIFICADA = "copia_certificada", "Copia certificada"
        DIGITAL = "digital", "Digital"

    class Expide(models.TextChoices):
        PARTICULAR = "particular", "Particular"
        MUNICIPIO = "municipio", "Municipio"
        ESTADO = "estado", "Estado"
        FEDERACION = "federacion", "Federación"

    tramite = models.ForeignKey(Tramite, related_name="requisitos", on_delete=models.CASCADE)
    orden = models.PositiveSmallIntegerField(default=1)
    nombre = models.CharField(max_length=250)
    fundamento = models.CharField("fundamento (artículo)", max_length=200, blank=True)
    formato = models.CharField(max_length=20, choices=Formato.choices, default=Formato.DIGITAL)
    quien_expide = models.CharField("quién lo expide", max_length=12, choices=Expide.choices, default=Expide.PARTICULAR)
    gobierno_ya_lo_tiene = models.BooleanField("el gobierno ya lo tiene", default=False)

    class Meta:
        ordering = ["orden", "id"]

    def __str__(self):
        return self.nombre

    def alertas(self):
        """Señales de que el requisito contradice la ley y debe simplificarse."""
        avisos = []
        if self.formato == self.Formato.COPIA_SIMPLE:
            avisos.append("Pide copia simple (art. 19 fr. IV).")
        if self.gobierno_ya_lo_tiene or self.quien_expide == self.Expide.MUNICIPIO:
            avisos.append("El municipio ya lo expide o lo tiene (art. 19 fr. I).")
        if not self.fundamento.strip():
            avisos.append("Sin fundamento jurídico (art. 19 fr. VIII).")
        return avisos
