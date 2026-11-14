from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from nucleo.models import Dependencia, Municipio

from .models import Tramite


def _visibles(municipio):
    """Trámites que se muestran al público: todo lo del municipio que no esté archivado."""
    return Tramite.objects.filter(municipio=municipio).exclude(estatus=Tramite.Estatus.ARCHIVADO)


def salud(request):
    return HttpResponse("ok", content_type="text/plain")


def inicio(request):
    municipios = Municipio.objects.filter(activo=True).annotate(
        total=Count("tramite", filter=~Q(tramite__estatus=Tramite.Estatus.ARCHIVADO))
    )
    return render(request, "catalogo/inicio.html", {"municipios": municipios})


def catalogo(request, municipio_slug):
    municipio = get_object_or_404(Municipio, slug=municipio_slug, activo=True)
    tramites = _visibles(municipio).select_related("dependencia")

    busqueda = request.GET.get("q", "").strip()[:80]
    dependencia_id = request.GET.get("dependencia", "")
    canal = request.GET.get("canal", "")

    if busqueda:
        tramites = tramites.filter(
            Q(nombre__icontains=busqueda) | Q(descripcion__icontains=busqueda) | Q(clave__icontains=busqueda)
        )
    if dependencia_id.isdigit():
        tramites = tramites.filter(dependencia_id=int(dependencia_id))
    if canal in Tramite.Canal.values:
        tramites = tramites.filter(canal=canal)

    pagina = Paginator(tramites, 30).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    dependencias = (
        Dependencia.objects.filter(municipio=municipio, activo=True)
        .annotate(total=Count("tramite", filter=~Q(tramite__estatus=Tramite.Estatus.ARCHIVADO)))
        .filter(total__gt=0)
    )
    return render(request, "catalogo/catalogo.html", {
        "municipio": municipio,
        "pagina": pagina,
        "total": pagina.paginator.count,
        "busqueda": busqueda,
        "dependencia_id": dependencia_id,
        "canal": canal,
        "canales": Tramite.Canal.choices,
        "dependencias": dependencias,
        "parametros": parametros.urlencode(),
    })


def ficha(request, municipio_slug, clave):
    municipio = get_object_or_404(Municipio, slug=municipio_slug, activo=True)
    tramite = get_object_or_404(_visibles(municipio).select_related("dependencia"), clave=clave)
    return render(request, "catalogo/ficha.html", {
        "municipio": municipio,
        "tramite": tramite,
        "requisitos": tramite.requisitos.all(),
    })
