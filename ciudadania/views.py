"""Registro, acceso y perfil de la ciudadanía."""
import hmac
import secrets
from datetime import date

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from nucleo.bitacora import ip_de, registrar
from nucleo.models import EventoBitacora

from . import avisos, llave_mx, renapo, seguridad, sesion
from .forms import AvisoForm, CodigoForm, ContactoForm, CurpForm, IdentidadForm
from .models import CodigoUnUso, IdentidadVinculada, NivelConfianza, Persona

REGISTRO = "registro_en_curso"
ACCESO = "acceso_en_curso"
PASOS = ["curp", "identidad", "contacto", "codigo", "aviso"]


# --- Utilidades ----------------------------------------------------------

def _respuesta_a_sesion(respuesta):
    return {
        "nombres": respuesta.nombres,
        "primer_apellido": respuesta.primer_apellido,
        "segundo_apellido": respuesta.segundo_apellido,
        "fecha_nacimiento": respuesta.fecha_nacimiento.isoformat() if respuesta.fecha_nacimiento else "",
        "sexo": respuesta.sexo,
        "entidad_nacimiento": respuesta.entidad_nacimiento,
        "simulada": respuesta.simulada,
    }


def consultar_renapo(request, curp, *, persona=None, municipio=None):
    """Consulta RENAPO y deja constancia en la bitácora. Devuelve (respuesta, mensaje_de_error)."""
    try:
        respuesta = renapo.consultar_curp(curp, municipio=municipio)
    except renapo.ServicioNoDisponible:
        return None, ("En este momento no podemos validar tu CURP con RENAPO. "
                      "Intenta más tarde o acude a la ventanilla del ayuntamiento.")
    registrar(
        EventoBitacora.Accion.CONSULTA_RENAPO,
        f"Consulta de la CURP {seguridad.enmascarar_curp(curp)} ({'encontrada' if respuesta.encontrada else 'no encontrada'})",
        request=request, persona=persona, municipio=municipio,
    )
    if not respuesta.encontrada:
        if respuesta.estatus == "baja":
            return None, "RENAPO reporta esta CURP como dada de baja. Acude a la ventanilla del ayuntamiento para orientarte."
        return None, respuesta.motivo or "RENAPO no encontró esta CURP. Revisa que esté bien escrita."
    return respuesta, ""


def crear_persona(curp, datos_renapo, **extra):
    fecha = datos_renapo.get("fecha_nacimiento")
    return Persona.objects.create(
        curp=curp,
        nombres=datos_renapo["nombres"],
        primer_apellido=datos_renapo["primer_apellido"],
        segundo_apellido=datos_renapo.get("segundo_apellido", ""),
        fecha_nacimiento=date.fromisoformat(fecha) if fecha else None,
        sexo=datos_renapo.get("sexo", ""),
        entidad_nacimiento=datos_renapo.get("entidad_nacimiento", ""),
        renapo_validado=timezone.now(),
        renapo_simulado=datos_renapo.get("simulada", False),
        **extra,
    )


def _registro(request):
    return request.session.get(REGISTRO) or {}


def _en_paso(request, paso):
    """Verdadero si el registro en curso ya llegó al paso pedido."""
    actual = _registro(request).get("paso")
    return actual in PASOS and PASOS.index(actual) >= PASOS.index(paso)


def _ir_a(request, paso):
    datos = _registro(request)
    datos["paso"] = paso
    request.session[REGISTRO] = datos
    return redirect(f"ciudadania:registro_{paso}")


# --- Páginas generales ---------------------------------------------------

def entrar(request):
    if sesion.persona_actual(request):
        return redirect("ciudadania:perfil")
    return render(request, "ciudadania/entrar.html")


def privacidad(request):
    return render(request, "ciudadania/privacidad.html")


# --- Registro de cuenta municipal ---------------------------------------

def registro_curp(request):
    form = CurpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        curp = form.cleaned_data["curp"]
        ip = ip_de(request) or "sin-ip"
        if seguridad.excede_limite("consulta_curp_ip", ip):
            form.add_error(None, "Hiciste demasiadas consultas. Espera una hora e inténtalo de nuevo.")
        elif Persona.objects.filter(curp=curp).exists():
            request.session[ACCESO] = {"curp": curp}
            messages.info(request, "Esta CURP ya tiene una cuenta. Para entrar, te enviaremos un código a tu correo o celular.")
            return redirect("ciudadania:acceso")
        else:
            seguridad.anotar_intento("consulta_curp_ip", ip)
            respuesta, error = consultar_renapo(request, curp)
            if error:
                form.add_error("curp", error)
            else:
                request.session[REGISTRO] = {"curp": curp, "renapo": _respuesta_a_sesion(respuesta), "paso": "curp"}
                return _ir_a(request, "identidad")
    return render(request, "ciudadania/registro_curp.html", {"form": form, "paso": 1})


def registro_identidad(request):
    if not _en_paso(request, "identidad"):
        return redirect("ciudadania:registro_curp")
    datos = _registro(request)
    form = IdentidadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        curp = datos["curp"]
        if seguridad.excede_limite("identidad_curp", curp):
            form.add_error(None, "Se agotaron los intentos para esta CURP. Espera una hora o acude a la ventanilla del ayuntamiento.")
        else:
            coincide = (
                seguridad.normalizar_nombre(form.cleaned_data["nombres"]) == seguridad.normalizar_nombre(datos["renapo"]["nombres"])
                and seguridad.normalizar_nombre(form.cleaned_data["primer_apellido"]) == seguridad.normalizar_nombre(datos["renapo"]["primer_apellido"])
            )
            if coincide:
                return _ir_a(request, "contacto")
            seguridad.anotar_intento("identidad_curp", curp)
            form.add_error(None, "El nombre no coincide con el registrado en RENAPO para esta CURP. Escríbelo como aparece en tu acta de nacimiento.")
    return render(request, "ciudadania/registro_identidad.html", {
        "form": form, "paso": 2, "curp_oculta": seguridad.enmascarar_curp(datos["curp"]),
        "simulada": datos["renapo"].get("simulada"),
    })


def _enviar_codigo(request, form, curp, proposito, destino):
    """Aplica límites, emite y envía el código. Devuelve True si se envió."""
    ip = ip_de(request) or "sin-ip"
    if seguridad.excede_limite("codigo_curp", curp) or seguridad.excede_limite("codigo_ip", ip):
        form.add_error(None, "Pediste demasiados códigos. Espera una hora e inténtalo de nuevo.")
        return False
    seguridad.anotar_intento("codigo_curp", curp)
    seguridad.anotar_intento("codigo_ip", ip)
    codigo = seguridad.emitir_codigo(curp, proposito, destino)
    try:
        avisos.enviar_codigo(destino, codigo)
    except Exception:  # noqa: BLE001 - cualquier falla del proveedor se informa igual
        form.add_error(None, "No pudimos enviar el código. Revisa el dato o intenta más tarde.")
        return False
    return True


def registro_contacto(request):
    if not _en_paso(request, "contacto"):
        return redirect("ciudadania:registro_curp")
    datos = _registro(request)
    form = ContactoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        destino = form.cleaned_data["destino"]
        if _enviar_codigo(request, form, datos["curp"], CodigoUnUso.Proposito.REGISTRO, destino):
            datos["destino"] = destino
            datos["medio"] = form.cleaned_data["medio"]
            request.session[REGISTRO] = datos
            return _ir_a(request, "codigo")
    return render(request, "ciudadania/registro_contacto.html", {"form": form, "paso": 3})


def registro_codigo(request):
    if not _en_paso(request, "codigo"):
        return redirect("ciudadania:registro_curp")
    datos = _registro(request)
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        correcto, mensaje = seguridad.verificar_codigo(datos["curp"], CodigoUnUso.Proposito.REGISTRO, form.cleaned_data["codigo"])
        if correcto:
            datos["contacto_confirmado"] = True
            request.session[REGISTRO] = datos
            return _ir_a(request, "aviso")
        form.add_error("codigo", mensaje)
    return render(request, "ciudadania/codigo.html", {
        "form": form, "paso": 4, "destino": seguridad.enmascarar_destino(datos.get("destino", "")),
        "reenviar": "ciudadania:registro_contacto", "titulo": "Confirma tu medio de contacto",
    })


def registro_aviso(request):
    if not _en_paso(request, "aviso") or not _registro(request).get("contacto_confirmado"):
        return redirect("ciudadania:registro_curp")
    datos = _registro(request)
    form = AvisoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contacto = {"correo": datos["destino"]} if datos["medio"] == "correo" else {"telefono": datos["destino"]}
        try:
            with transaction.atomic():
                persona = crear_persona(
                    datos["curp"], datos["renapo"], contacto_confirmado=True, acepto_aviso=timezone.now(),
                    nivel_confianza=NivelConfianza.BASICO, **contacto,
                )
                IdentidadVinculada.objects.create(
                    persona=persona, proveedor=IdentidadVinculada.Proveedor.CUENTA_MUNICIPAL,
                    sujeto=persona.curp, nivel=NivelConfianza.BASICO,
                )
        except IntegrityError:
            request.session.pop(REGISTRO, None)
            messages.info(request, "Esta CURP ya tiene una cuenta. Inicia sesión.")
            return redirect("ciudadania:acceso")
        registrar(EventoBitacora.Accion.REGISTRO_CIUDADANO, "Registro de cuenta municipal en línea", request=request, persona=persona)
        avisos.avisar_al_titular(persona, "Se creó una cuenta en la plataforma de trámites municipales con tu CURP. "
                                          "Si no fuiste tú, acude a la ventanilla de tu ayuntamiento.")
        request.session.pop(REGISTRO, None)
        sesion.iniciar(request, persona, IdentidadVinculada.Proveedor.CUENTA_MUNICIPAL, NivelConfianza.BASICO)
        messages.success(request, "Tu cuenta quedó creada.")
        return redirect("ciudadania:perfil")
    return render(request, "ciudadania/registro_aviso.html", {"form": form, "paso": 5})


# --- Acceso con código ----------------------------------------------------

def acceso(request):
    inicial = {"curp": (request.session.get(ACCESO) or {}).get("curp", "")}
    form = CurpForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        curp = form.cleaned_data["curp"]
        persona = Persona.objects.filter(curp=curp, activa=True, contacto_confirmado=True).first()
        enviado = True
        if persona:
            enviado = _enviar_codigo(request, form, curp, CodigoUnUso.Proposito.ACCESO, persona.destino_codigo)
        else:
            # Mismos límites y misma respuesta, para no revelar qué CURP tienen cuenta.
            ip = ip_de(request) or "sin-ip"
            if seguridad.excede_limite("codigo_curp", curp) or seguridad.excede_limite("codigo_ip", ip):
                form.add_error(None, "Pediste demasiados códigos. Espera una hora e inténtalo de nuevo.")
                enviado = False
            else:
                seguridad.anotar_intento("codigo_curp", curp)
                seguridad.anotar_intento("codigo_ip", ip)
        if enviado:
            request.session[ACCESO] = {"curp": curp}
            return redirect("ciudadania:acceso_codigo")
    return render(request, "ciudadania/acceso.html", {"form": form})


def acceso_codigo(request):
    curp = (request.session.get(ACCESO) or {}).get("curp")
    if not curp:
        return redirect("ciudadania:acceso")
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        correcto, mensaje = seguridad.verificar_codigo(curp, CodigoUnUso.Proposito.ACCESO, form.cleaned_data["codigo"])
        persona = Persona.objects.filter(curp=curp, activa=True).first() if correcto else None
        if persona:
            request.session.pop(ACCESO, None)
            # La cuenta municipal llega como máximo a nivel 2; el 3 exige Llave MX Verificada.
            nivel = min(persona.nivel_confianza, NivelConfianza.VERIFICADO)
            sesion.iniciar(request, persona, IdentidadVinculada.Proveedor.CUENTA_MUNICIPAL, nivel)
            return redirect("ciudadania:perfil")
        form.add_error("codigo", mensaje or "El código no es correcto.")
    return render(request, "ciudadania/codigo.html", {
        "form": form, "destino": "", "reenviar": "ciudadania:acceso", "titulo": "Escribe tu código de acceso",
        "neutral": True,
    })


# --- Llave MX ------------------------------------------------------------

def llave_mx_inicio(request):
    estado = secrets.token_urlsafe(24)
    request.session["llave_mx_estado"] = estado
    try:
        return redirect(llave_mx.url_autorizacion(request, estado))
    except llave_mx.LlaveMXNoDisponible:
        messages.warning(request, "El acceso con Llave MX todavía no está disponible. Usa tu cuenta municipal.")
        return redirect("ciudadania:entrar")


def llave_mx_retorno(request):
    esperado = request.session.pop("llave_mx_estado", "")
    recibido = request.GET.get("state", "")
    if not esperado or not hmac.compare_digest(esperado, recibido):
        messages.error(request, "La respuesta de Llave MX no corresponde a esta sesión. Vuelve a intentarlo.")
        return redirect("ciudadania:entrar")
    try:
        identidad = llave_mx.canjear_codigo(request.GET.get("code", ""))
    except llave_mx.LlaveMXNoDisponible:
        identidad = None
    if identidad is None:
        messages.error(request, "No se pudo completar el acceso con Llave MX. Vuelve a intentarlo.")
        return redirect("ciudadania:entrar")

    vinculo = IdentidadVinculada.objects.filter(proveedor=IdentidadVinculada.Proveedor.LLAVE_MX, sujeto=identidad.sujeto).select_related("persona").first()
    if vinculo and vinculo.persona.curp != identidad.curp:
        messages.error(request, "La CURP de Llave MX no coincide con la cuenta vinculada. Acude a la ventanilla del ayuntamiento.")
        return redirect("ciudadania:entrar")

    persona = Persona.objects.filter(curp=identidad.curp).first()
    if persona is None:
        respuesta, error = consultar_renapo(request, identidad.curp)
        if error:
            messages.error(request, error)
            return redirect("ciudadania:entrar")
        persona = crear_persona(identidad.curp, _respuesta_a_sesion(respuesta), nivel_confianza=identidad.nivel)
        registrar(EventoBitacora.Accion.REGISTRO_CIUDADANO, "Registro de cuenta con Llave MX", request=request, persona=persona)
    if not persona.activa:
        messages.error(request, "Esta cuenta está suspendida. Acude a la ventanilla del ayuntamiento.")
        return redirect("ciudadania:entrar")

    otra_llave = persona.identidades.filter(proveedor=IdentidadVinculada.Proveedor.LLAVE_MX).exclude(sujeto=identidad.sujeto)
    if vinculo is None and otra_llave.exists():
        messages.error(request, "Tu perfil ya tiene vinculada otra cuenta Llave MX. Acude a la ventanilla del ayuntamiento.")
        return redirect("ciudadania:entrar")
    if vinculo is None:
        IdentidadVinculada.objects.create(persona=persona, proveedor=IdentidadVinculada.Proveedor.LLAVE_MX,
                                          sujeto=identidad.sujeto, nivel=identidad.nivel)
        registrar(EventoBitacora.Accion.VINCULACION, "Se vinculó Llave MX a la cuenta", request=request, persona=persona)
        avisos.avisar_al_titular(persona, "Se vinculó una cuenta Llave MX a tu perfil de trámites municipales. "
                                          "Si no fuiste tú, acude a la ventanilla de tu ayuntamiento.")
    elif vinculo.nivel != identidad.nivel:
        vinculo.nivel = identidad.nivel
        vinculo.save(update_fields=["nivel"])
    persona.subir_nivel(identidad.nivel)
    sesion.iniciar(request, persona, IdentidadVinculada.Proveedor.LLAVE_MX, identidad.nivel)
    if not persona.acepto_aviso:
        return redirect("ciudadania:aceptar_aviso")
    return redirect("ciudadania:perfil")


# --- Perfil --------------------------------------------------------------

@sesion.requiere_persona
def aceptar_aviso(request):
    persona = sesion.persona_actual(request)
    form = AvisoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        persona.acepto_aviso = timezone.now()
        persona.save(update_fields=["acepto_aviso"])
        return redirect("ciudadania:perfil")
    return render(request, "ciudadania/registro_aviso.html", {"form": form, "sin_pasos": True})


@sesion.requiere_persona
def perfil(request):
    persona = sesion.persona_actual(request)
    if not persona.acepto_aviso:
        return redirect("ciudadania:aceptar_aviso")
    return render(request, "ciudadania/perfil.html", {
        "persona": persona,
        "sesion": sesion.datos(request),
        "nivel_sesion": sesion.nivel_sesion(request),
        "niveles": NivelConfianza,
        "identidades": persona.identidades.all(),
        "tiene_llave": persona.identidades.filter(proveedor=IdentidadVinculada.Proveedor.LLAVE_MX).exists(),
        "verificaciones": persona.verificaciones.select_related("municipio")[:5],
        "eventos": persona.eventos.select_related("usuario", "municipio")[:15],
        "destino": seguridad.enmascarar_destino(persona.destino_codigo) if persona.destino_codigo else "",
    })


@require_POST
def salir(request):
    sesion.cerrar(request)
    messages.info(request, "Cerraste tu sesión.")
    return redirect("catalogo:inicio")
