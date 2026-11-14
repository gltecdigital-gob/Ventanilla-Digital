from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from nucleo.admin_base import municipio_de
from nucleo.bitacora import registrar
from nucleo.models import Dependencia, EventoBitacora, Municipio

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "municipio", "dependencia", "rol", "is_active")
    list_filter = ("municipio", "rol", "is_active")

    def get_list_filter(self, request):
        filtros = list(super().get_list_filter(request))
        if not request.user.is_superuser:
            filtros.remove("municipio")
        return filtros
    fieldsets = UserAdmin.fieldsets + (("Adscripción", {"fields": ("municipio", "dependencia", "rol")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Adscripción", {"fields": ("municipio", "dependencia", "rol")}),)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        municipio = municipio_de(request)
        return qs.filter(municipio=municipio, is_superuser=False) if municipio else qs.none()

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        # La autoridad municipal no puede otorgar permisos de plataforma.
        limpios = []
        for nombre, opciones in fieldsets:
            campos = tuple(c for c in opciones["fields"] if c not in ("is_superuser", "user_permissions", "municipio"))
            limpios.append((nombre, {**opciones, "fields": campos}))
        return limpios

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            municipio = municipio_de(request)
            if db_field.name == "municipio":
                kwargs["queryset"] = Municipio.objects.filter(pk=getattr(municipio, "pk", None))
            elif db_field.name == "dependencia":
                kwargs["queryset"] = Dependencia.objects.filter(municipio=municipio)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.municipio = municipio_de(request)
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
        accion = EventoBitacora.Accion.MODIFICAR if change else EventoBitacora.Accion.CREAR
        registrar(accion, f"servidor público: {obj.get_username()}", request=request, objeto=obj,
                  cambios={"campos": [c for c in form.changed_data if "password" not in c]} if change else {})
