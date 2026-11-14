from django.contrib import admin

from .models import IdentidadVinculada, Persona, VerificacionPresencial


class SoloLectura(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class IdentidadEnLinea(SoloLectura):
    model = IdentidadVinculada
    fields = ("proveedor", "nivel", "vinculada", "ultimo_uso")
    readonly_fields = fields


class VerificacionEnLinea(SoloLectura):
    model = VerificacionPresencial
    fields = ("fecha", "municipio", "servidor", "tipo_identificacion", "ultimos_digitos")
    readonly_fields = fields


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    """Solo el administrador de la plataforma ve personas aquí; el personal usa la ventanilla.

    Los datos de RENAPO no se editan. El administrador solo puede suspender o reactivar.
    """

    list_display = ("curp", "nombre_completo", "nivel_confianza", "contacto_confirmado", "activa", "creada")
    list_filter = ("nivel_confianza", "activa", "renapo_simulado")
    search_fields = ("curp", "primer_apellido")
    inlines = [IdentidadEnLinea, VerificacionEnLinea]
    exclude = ()

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Persona._meta.fields if f.name != "activa"]
