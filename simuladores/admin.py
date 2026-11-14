from django.contrib import admin

from .models import MensajeSimulado


@admin.register(MensajeSimulado)
class MensajeSimuladoAdmin(admin.ModelAdmin):
    list_display = ("creado", "canal", "destino", "asunto")

    def has_module_permission(self, request):
        return request.user.is_superuser
