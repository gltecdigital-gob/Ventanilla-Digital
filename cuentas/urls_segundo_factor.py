from django.urls import path

from . import views_segundo_factor as v

app_name = "segundo_factor"

urlpatterns = [
    path("configurar/", v.configurar, name="configurar"),
    path("verificar/", v.verificar, name="verificar"),
    path("salir/", v.salir, name="salir"),
]
