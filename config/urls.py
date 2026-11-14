from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Plataforma Municipal de Trámites Digitales"
admin.site.site_title = "Panel de administración"
admin.site.index_title = "Panel de la Autoridad Municipal de Simplificación y Digitalización"

urlpatterns = [
    path("panel/", admin.site.urls),
    path("", include("catalogo.urls")),
]
