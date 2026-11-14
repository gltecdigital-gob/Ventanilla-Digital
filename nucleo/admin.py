from django.contrib import admin

from .admin_base import AdminConBitacora, AdminMunicipal, municipio_de
from .models import Dependencia, EventoBitacora, Municipio


@admin.register(Municipio)
class MunicipioAdmin(AdminConBitacora):
    list_display = ("nombre", "estado", "slug", "activo")
    prepopulated_fields = {"slug": ("nombre",)}

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        municipio = municipio_de(request)
        return qs.filter(pk=getattr(municipio, "pk", None))

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Dependencia)
class DependenciaAdmin(AdminMunicipal):
    list_display = ("nombre", "siglas", "municipio", "activo")
    list_filter = ("municipio", "activo")
    search_fields = ("nombre", "siglas")


@admin.register(EventoBitacora)
class EventoBitacoraAdmin(admin.ModelAdmin):
    """La bitácora solo se consulta."""

    list_display = ("fecha", "accion", "descripcion", "usuario", "municipio", "ip")
    list_filter = ("accion", "municipio")
    search_fields = ("descripcion", "usuario__username")
    date_hierarchy = "fecha"

    def get_list_filter(self, request):
        filtros = list(super().get_list_filter(request))
        if not request.user.is_superuser:
            filtros.remove("municipio")
        return filtros

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("usuario", "municipio")
        if request.user.is_superuser:
            return qs
        municipio = municipio_de(request)
        return qs.filter(municipio=municipio) if municipio else qs.none()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
