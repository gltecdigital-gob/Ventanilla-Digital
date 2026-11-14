from django.urls import path

from . import views

app_name = "simuladores"

urlpatterns = [
    path("llave-mx/autorizar/", views.llave_mx_autorizar, name="llave_mx_autorizar"),
    path("buzon/", views.buzon, name="buzon"),
]
