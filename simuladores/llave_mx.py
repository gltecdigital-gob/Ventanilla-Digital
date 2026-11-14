"""Simulador de Llave MX: imita el ida y vuelta de un inicio de sesión federado."""
import hashlib
import secrets

from django.core.cache import cache

VIGENCIA = 300  # segundos


def emitir(curp, verificada):
    codigo = secrets.token_urlsafe(24)
    sujeto = "llavemx-sim-" + hashlib.sha256(curp.encode()).hexdigest()[:16]
    cache.set(f"llave_mx_sim:{codigo}", {"curp": curp, "sujeto": sujeto, "verificada": verificada}, VIGENCIA)
    return codigo


def canjear(codigo):
    if not codigo:
        return None
    clave = f"llave_mx_sim:{codigo}"
    datos = cache.get(clave)
    cache.delete(clave)  # un solo uso
    return datos
