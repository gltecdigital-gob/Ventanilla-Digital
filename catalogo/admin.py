from django.contrib import admin, messages

from cuentas.models import Usuario
from nucleo.admin_base import AdminMunicipal
from nucleo.bitacora import registrar
from nucleo.models import EventoBitacora

from .models import Requisito, Tramite


class RequisitoEnLinea(admin.TabularInline):
    model = Requisito
    extra = 1
    fields = ("orden", "nombre", "fundamento", "formato", "quien_expide", "gobierno_ya_lo_tiene")


@admin.register(Tramite)
class TramiteAdmin(AdminMunicipal):
    list_display = ("clave", "nombre", "dependencia", "municipio", "ruta", "canal", "estatus", "ficha_completa")
    list_filter = ("municipio", "estatus", "ruta", "canal", "tipo", ("dependencia", admin.RelatedOnlyFieldListFilter))
    search_fields = ("clave", "nombre", "descripcion")
    list_per_page = 50
    inlines = [RequisitoEnLinea]
    actions = ["publicar"]
    fieldsets = (
        ("Identificación", {"fields": ("municipio", "clave", "nombre", "tipo", "dependencia", "descripcion", "modalidad", "canal", "fundamento")}),
        ("Resolución", {"fields": ("plazo_resolucion_dias", "ficta", "plazo_prevencion_dias", "inspeccion", "vigencia")}),
        ("Costo", {"fields": ("costo", "costo_detalle", "formas_pago")}),
        ("Atención", {"fields": ("oficinas", "horarios", "contacto")}),
        ("Gestión", {"fields": ("ruta", "nivel_confianza", "clave_catalogo_nacional", "estatus")}),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        return [(n, {**o, "fields": tuple(c for c in o["fields"] if c != "municipio")}) for n, o in fieldsets]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("dependencia", "municipio")
        usuario = request.user
        # Un Enlace solo trabaja los trámites de su dependencia.
        if not usuario.is_superuser and usuario.rol == Usuario.Rol.ENLACE:
            qs = qs.filter(dependencia=usuario.dependencia)
        return qs

    @admin.display(boolean=True, description="Ficha completa")
    def ficha_completa(self, obj):
        return not obj.faltantes_para_publicar()

    @admin.action(description="Publicar los trámites seleccionados")
    def publicar(self, request, queryset):
        publicados = 0
        for tramite in queryset:
            faltan = tramite.faltantes_para_publicar()
            if faltan:
                self.message_user(request, f"{tramite.clave} no se publicó. Falta: {'; '.join(faltan)}.", messages.WARNING)
                continue
            if tramite.estatus != Tramite.Estatus.PUBLICADO:
                tramite.estatus = Tramite.Estatus.PUBLICADO
                tramite.save(update_fields=["estatus", "actualizado"])
                registrar(EventoBitacora.Accion.PUBLICAR, f"trámite publicado: {tramite}", request=request, objeto=tramite)
                publicados += 1
        if publicados:
            self.message_user(request, f"Se publicaron {publicados} trámites.", messages.SUCCESS)
