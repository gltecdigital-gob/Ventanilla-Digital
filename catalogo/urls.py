from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("salud/", views.salud, name="salud"),
    path("<slug:municipio_slug>/", views.catalogo, name="catalogo"),
    path("<slug:municipio_slug>/tramite/<str:clave>/", views.ficha, name="ficha"),
]
