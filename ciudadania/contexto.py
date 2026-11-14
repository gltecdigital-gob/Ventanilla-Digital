from .sesion import persona_actual


def ciudadano(request):
    return {"ciudadano": persona_actual(request)}
