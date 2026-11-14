"""Códigos de un solo uso basados en tiempo (TOTP, RFC 6238).

Compatibles con las aplicaciones de autenticación comunes (Google Authenticator,
Microsoft Authenticator, FreeOTP, Authy).
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

PERIODO = 30
DIGITOS = 6


def generar_secreto():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _clave(secreto):
    relleno = "=" * (-len(secreto) % 8)
    return base64.b32decode(secreto.upper() + relleno)


def paso_actual(ahora=None):
    return int((time.time() if ahora is None else ahora) // PERIODO)


def codigo(secreto, paso, digitos=DIGITOS, algoritmo=hashlib.sha1, clave=None):
    resumen = hmac.new(clave if clave is not None else _clave(secreto), struct.pack(">Q", paso), algoritmo).digest()
    desplazamiento = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desplazamiento:desplazamiento + 4])[0] & 0x7FFFFFFF
    return str(numero % (10 ** digitos)).zfill(digitos)


def verificar(secreto, propuesto, ultimo_paso_usado=0, ahora=None, ventana=1):
    """Devuelve el paso aceptado, o None.

    Acepta el periodo actual y uno antes o después (relojes desfasados), pero nunca un
    paso igual o anterior al último usado: un código no sirve dos veces.
    """
    propuesto = (propuesto or "").replace(" ", "")
    if len(propuesto) != DIGITOS or not propuesto.isdigit():
        return None
    actual = paso_actual(ahora)
    for paso in range(actual - ventana, actual + ventana + 1):
        if paso > ultimo_paso_usado and hmac.compare_digest(codigo(secreto, paso), propuesto):
            return paso
    return None


def uri_aprovisionamiento(secreto, cuenta, emisor):
    etiqueta = quote(f"{emisor}:{cuenta}")
    return f"otpauth://totp/{etiqueta}?" + urlencode(
        {"secret": secreto, "issuer": emisor, "algorithm": "SHA1", "digits": DIGITOS, "period": PERIODO}
    )
