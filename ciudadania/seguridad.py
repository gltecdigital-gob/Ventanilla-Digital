"""Códigos de un solo uso, límites de intentos y enmascarado de datos."""
import hashlib
import hmac
import secrets
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import CodigoUnUso, RegistroIntento

VIGENCIA_CODIGO = timedelta(minutes=10)
INTENTOS_POR_CODIGO = 5

# (máximo de intentos, ventana)
LIMITES = {
    "consulta_curp_ip": (20, timedelta(hours=1)),
    "codigo_curp": (5, timedelta(hours=1)),
    "codigo_ip": (20, timedelta(hours=1)),
    "identidad_curp": (5, timedelta(hours=1)),
    "segundo_factor_usuario": (5, timedelta(minutes=15)),
}


def _huella(texto):
    return hmac.new(settings.SECRET_KEY.encode(), texto.encode(), hashlib.sha256).hexdigest()


# --- Límites de intentos -------------------------------------------------

def excede_limite(tipo, clave):
    maximo, ventana = LIMITES[tipo]
    desde = timezone.now() - ventana
    return RegistroIntento.objects.filter(tipo=tipo, clave=_huella(clave), creado__gte=desde).count() >= maximo


def anotar_intento(tipo, clave):
    RegistroIntento.objects.create(tipo=tipo, clave=_huella(clave))


def limpiar_intentos_viejos():
    RegistroIntento.objects.filter(creado__lt=timezone.now() - timedelta(days=1)).delete()


# --- Códigos de un solo uso ---------------------------------------------

def emitir_codigo(curp, proposito, destino):
    """Crea un código nuevo, invalida los anteriores y devuelve el código en claro para enviarlo."""
    CodigoUnUso.objects.filter(curp=curp, proposito=proposito, usado=False).update(usado=True)
    codigo = f"{secrets.randbelow(10**6):06d}"
    CodigoUnUso.objects.create(
        curp=curp, proposito=proposito, destino=destino,
        huella=_huella(f"{curp}:{proposito}:{codigo}"),
        expira=timezone.now() + VIGENCIA_CODIGO,
    )
    return codigo


def verificar_codigo(curp, proposito, codigo):
    """Devuelve (correcto, mensaje). Un código se usa una vez y admite 5 intentos."""
    registro = CodigoUnUso.objects.filter(curp=curp, proposito=proposito, usado=False).first()
    if registro is None or registro.expira < timezone.now():
        return False, "El código venció o ya no es válido. Pide uno nuevo."
    if registro.intentos >= INTENTOS_POR_CODIGO:
        return False, "Se agotaron los intentos para este código. Pide uno nuevo."
    registro.intentos += 1
    correcto = hmac.compare_digest(registro.huella, _huella(f"{curp}:{proposito}:{(codigo or '').strip()}"))
    if correcto:
        registro.usado = True
    registro.save(update_fields=["intentos", "usado"])
    if correcto:
        return True, ""
    restantes = INTENTOS_POR_CODIGO - registro.intentos
    return False, f"El código no es correcto. Te quedan {restantes} intento{'s' if restantes != 1 else ''}."


# --- Comparación y enmascarado ------------------------------------------

def normalizar_nombre(texto):
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )
    return " ".join(sin_acentos.upper().replace(".", " ").split())


def enmascarar_correo(correo):
    usuario, _, dominio = (correo or "").partition("@")
    if not dominio:
        return ""
    visible = usuario[:2] if len(usuario) > 3 else usuario[:1]
    return f"{visible}{'•' * 4}@{dominio}"


def enmascarar_telefono(telefono):
    return f"{'•' * 6}{telefono[-4:]}" if telefono else ""


def enmascarar_destino(destino):
    return enmascarar_correo(destino) if "@" in destino else enmascarar_telefono(destino)


def enmascarar_curp(curp):
    return f"{curp[:4]}{'•' * 10}{curp[-4:]}" if curp else ""
