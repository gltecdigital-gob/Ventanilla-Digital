"""Base del panel: separa los datos por municipio y anota todo en la bitácora."""
from django.contrib import admin

from .bitacora import registrar
from .models import Dependencia, EventoBitacora, Municipio


def municipio_de(request):
    """Municipio al que está limitado el usuario; None si es administrador de la plataforma."""
    if request.user.is_superuser:
        return None
    return request.user.municipio


class AdminConBitacora(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        accion = EventoBitacora.Accion.MODIFICAR if change else EventoBitacora.Accion.CREAR
        cambios = {"campos": list(form.changed_data)} if change else {}
        registrar(accion, f"{obj._meta.verbose_name}: {obj}", request=request, objeto=obj, cambios=cambios)

    def delete_model(self, request, obj):
        registrar(EventoBitacora.Accion.ELIMINAR, f"{obj._meta.verbose_name}: {obj}", request=request, objeto=obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            registrar(EventoBitacora.Accion.ELIMINAR, f"{obj._meta.verbose_name}: {obj}", request=request, objeto=obj)
        super().delete_queryset(request, queryset)


class AdminMunicipal(AdminConBitacora):
    """Panel de un modelo que pertenece a un municipio.

    Quien no es administrador de la plataforma solo ve y edita lo de su municipio,
    y no puede asignar registros a otro.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        municipio = municipio_de(request)
        if request.user.is_superuser:
            return qs
        if municipio is None:
            return qs.none()
        return qs.filter(municipio=municipio)

    def get_exclude(self, request, obj=None):
        excluidos = list(super().get_exclude(request, obj) or [])
        if not request.user.is_superuser:
            excluidos.append("municipio")
        return excluidos

    def get_list_filter(self, request):
        filtros = list(super().get_list_filter(request))
        if not request.user.is_superuser and "municipio" in filtros:
            filtros.remove("municipio")
        return filtros

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        municipio = municipio_de(request)
        if not request.user.is_superuser:
            if db_field.name == "municipio":
                kwargs["queryset"] = Municipio.objects.filter(pk=getattr(municipio, "pk", None))
            elif db_field.name == "dependencia":
                kwargs["queryset"] = Dependencia.objects.filter(municipio=municipio)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.municipio = municipio_de(request)
        super().save_model(request, obj, form, change)
