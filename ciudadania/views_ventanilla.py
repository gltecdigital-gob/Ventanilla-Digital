"""Ventanilla asistida: el personal municipal registra y verifica en persona.

Sirve a quien no usa internet, no tiene correo ni celular, o necesita subir a
nivel 2 sin Llave MX. Toda consulta queda en la bitácora a nombre del servidor público.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from nucleo.bitacora import registrar
from nucleo.models import EventoBitacora
from simuladores.curp import validar_formato

from . import avisos, seguridad
from django.utils import timezone

from .forms import AltaVentanillaForm, CodigoForm, ContactoVentanillaForm, CurpForm, VerificacionForm
from .models import CodigoUnUso, IdentidadVinculada, NivelConfianza, Persona, VerificacionPresencial
from .views import _respuesta_a_sesion, consultar_renapo, crear_persona

ALTA = "ventanilla_alta"


def personal_de_ventanilla(vista):
    @login_required(login_url="admin:login")
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        usuario = request.user
        if not usuario.has_perm("ciudadania.verificar_identidad"):
            raise PermissionDenied("No tienes permiso para la ventanilla.")
        if usuario.municipio is None:
            raise PermissionDenied("Tu cuenta no está adscrita a un municipio.")
        return vista(request, *args, **kwargs)

    return envoltura


def _verificar(request, persona, form):
    VerificacionPresencial.objects.create(
        persona=persona, servidor=request.user, municipio=request.user.municipio,
        tipo_identificacion=form.cleaned_data["tipo_identificacion"],
        ultimos_digitos=form.cleaned_data["ultimos_digitos"],
    )
    persona.subir_nivel(NivelConfianza.VERIFICADO)
    registrar(EventoBitacora.Accion.VERIFICACION_PRESENCIAL, "Identidad verificada en ventanilla",
              request=request, persona=persona, municipio=request.user.municipio,
              cambios={"identificacion": form.cleaned_data["tipo_identificacion"]})


@personal_de_ventanilla
def inicio(request):
    form = CurpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        curp = form.cleaned_data["curp"]
        if Persona.objects.filter(curp=curp).exists():
            return redirect("ventanilla:persona", curp=curp)
        respuesta, error = consultar_renapo(request, curp, municipio=request.user.municipio)
        if error:
            form.add_error("curp", error)
        else:
            request.session[ALTA] = {"curp": curp, "renapo": _respuesta_a_sesion(respuesta)}
            return redirect("ventanilla:alta")
    return render(request, "ventanilla/inicio.html", {"form": form})


@personal_de_ventanilla
def alta(request):
    datos = request.session.get(ALTA)
    if not datos:
        return redirect("ventanilla:inicio")
    form = AltaVentanillaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                persona = crear_persona(datos["curp"], datos["renapo"], nivel_confianza=NivelConfianza.BASICO,
                                        acepto_aviso=timezone.now())
                IdentidadVinculada.objects.create(
                    persona=persona, proveedor=IdentidadVinculada.Proveedor.CUENTA_MUNICIPAL,
                    sujeto=persona.curp, nivel=NivelConfianza.VERIFICADO,
                )
                registrar(EventoBitacora.Accion.REGISTRO_CIUDADANO, "Registro en ventanilla asistida",
                          request=request, persona=persona, municipio=request.user.municipio)
                _verificar(request, persona, form)
        except IntegrityError:
            messages.info(request, "Esta CURP ya estaba registrada.")
            return redirect("ventanilla:persona", curp=datos["curp"])
        request.session.pop(ALTA, None)
        messages.success(request, "Persona registrada con nivel 2. Si tiene correo o celular, regístralo para que pueda entrar en línea.")
        return redirect("ventanilla:contacto", curp=persona.curp)
    fecha = datos["renapo"].get("fecha_nacimiento", "")
    fecha_legible = "/".join(reversed(fecha.split("-"))) if fecha else ""
    return render(request, "ventanilla/alta.html", {"form": form, "datos": datos["renapo"], "curp": datos["curp"],
                                                     "fecha_nacimiento": fecha_legible})


@personal_de_ventanilla
def persona(request, curp):
    if not validar_formato(curp)[0]:
        raise PermissionDenied
    persona = get_object_or_404(Persona, curp=curp)
    form = VerificacionForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            _verificar(request, persona, form)
            avisos.avisar_al_titular(persona, f"Tu identidad fue verificada en la ventanilla de {request.user.municipio}. "
                                              "Si no fuiste tú, acude de inmediato al ayuntamiento.")
            messages.success(request, "Identidad verificada. La persona ya tiene nivel 2.")
            return redirect("ventanilla:persona", curp=curp)
    else:
        registrar(EventoBitacora.Accion.CONSULTA_DATOS, "Consulta del perfil en ventanilla",
                  request=request, persona=persona, municipio=request.user.municipio)
    return render(request, "ventanilla/persona.html", {
        "persona": persona, "form": form,
        "verificaciones": persona.verificaciones.select_related("servidor", "municipio")[:5],
        "destino": seguridad.enmascarar_destino(persona.destino_codigo) if persona.destino_codigo else "",
    })


@personal_de_ventanilla
def contacto(request, curp):
    persona = get_object_or_404(Persona, curp=curp)
    enviado = request.session.get("ventanilla_contacto") or {}
    enviado = enviado if enviado.get("curp") == curp else {}
    form_contacto = ContactoVentanillaForm(request.POST if request.POST.get("accion") == "enviar" else None)
    form_codigo = CodigoForm(request.POST if request.POST.get("accion") == "verificar" else None)

    if request.method == "POST" and request.POST.get("accion") == "enviar" and form_contacto.is_valid():
        destino = form_contacto.cleaned_data["destino"]
        codigo = seguridad.emitir_codigo(curp, CodigoUnUso.Proposito.REGISTRO, destino)
        try:
            avisos.enviar_codigo(destino, codigo)
        except Exception:  # noqa: BLE001
            form_contacto.add_error(None, "No se pudo enviar el código. Revisa el dato.")
        else:
            request.session["ventanilla_contacto"] = {"curp": curp, "destino": destino, "medio": form_contacto.cleaned_data["medio"]}
            return redirect("ventanilla:contacto", curp=curp)

    if request.method == "POST" and request.POST.get("accion") == "verificar" and enviado and form_codigo.is_valid():
        correcto, mensaje = seguridad.verificar_codigo(curp, CodigoUnUso.Proposito.REGISTRO, form_codigo.cleaned_data["codigo"])
        if correcto:
            persona.correo = enviado["destino"] if enviado["medio"] == "correo" else ""
            persona.telefono = enviado["destino"] if enviado["medio"] == "telefono" else ""
            persona.contacto_confirmado = True
            persona.save(update_fields=["correo", "telefono", "contacto_confirmado"])
            registrar(EventoBitacora.Accion.CONTACTO, "Medio de contacto confirmado en ventanilla",
                      request=request, persona=persona, municipio=request.user.municipio)
            request.session.pop("ventanilla_contacto", None)
            messages.success(request, "Contacto confirmado. La persona ya puede entrar en línea con su CURP.")
            return redirect("ventanilla:persona", curp=curp)
        form_codigo.add_error("codigo", mensaje)

    return render(request, "ventanilla/contacto.html", {
        "persona": persona, "form_contacto": form_contacto, "form_codigo": form_codigo,
        "enviado_a": seguridad.enmascarar_destino(enviado["destino"]) if enviado else "",
    })
