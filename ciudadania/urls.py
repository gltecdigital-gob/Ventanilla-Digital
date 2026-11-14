from django.urls import path

from . import views

app_name = "ciudadania"

urlpatterns = [
    path("", views.perfil, name="perfil"),
    path("entrar/", views.entrar, name="entrar"),
    path("registro/", views.registro_curp, name="registro_curp"),
    path("registro/identidad/", views.registro_identidad, name="registro_identidad"),
    path("registro/contacto/", views.registro_contacto, name="registro_contacto"),
    path("registro/codigo/", views.registro_codigo, name="registro_codigo"),
    path("registro/aviso/", views.registro_aviso, name="registro_aviso"),
    path("acceso/", views.acceso, name="acceso"),
    path("acceso/codigo/", views.acceso_codigo, name="acceso_codigo"),
    path("llave-mx/", views.llave_mx_inicio, name="llave_mx"),
    path("llave-mx/retorno/", views.llave_mx_retorno, name="llave_mx_retorno"),
    path("aviso/", views.aceptar_aviso, name="aceptar_aviso"),
    path("salir/", views.salir, name="salir"),
]
