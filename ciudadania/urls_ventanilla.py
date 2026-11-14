from django.urls import path

from . import views_ventanilla as v

app_name = "ventanilla"

urlpatterns = [
    path("", v.inicio, name="inicio"),
    path("alta/", v.alta, name="alta"),
    path("persona/<str:curp>/", v.persona, name="persona"),
    path("persona/<str:curp>/contacto/", v.contacto, name="contacto"),
]
