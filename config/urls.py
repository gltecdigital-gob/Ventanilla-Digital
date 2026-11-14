from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Plataforma Municipal de Trámites Digitales"
admin.site.site_title = "Panel de administración"
admin.site.index_title = "Panel de la Autoridad Municipal de Simplificación y Digitalización"

from ciudadania import views as ciudadania_views

urlpatterns = [
    path("panel/", admin.site.urls),
    path("cuenta/", include("ciudadania.urls")),
    path("ventanilla/", include("ciudadania.urls_ventanilla")),
    path("simuladores/", include("simuladores.urls")),
    path("privacidad/", ciudadania_views.privacidad, name="privacidad"),
    # Al final: el catálogo usa /<municipio>/ y no debe tapar las rutas anteriores.
    path("", include("catalogo.urls")),
]
