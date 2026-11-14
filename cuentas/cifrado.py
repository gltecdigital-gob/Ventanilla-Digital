"""Cifrado de secretos guardados en la base (por ejemplo, la semilla del segundo factor).

La llave viene de CLAVE_CIFRADO, distinta de SECRET_KEY, para que una copia de la base
sin la llave no permita generar códigos. En desarrollo, si no hay llave, se deriva de
SECRET_KEY.
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet():
    clave = getattr(settings, "CLAVE_CIFRADO", "")
    if not clave:
        clave = base64.urlsafe_b64encode(hashlib.sha256(("cifrado:" + settings.SECRET_KEY).encode()).digest()).decode()
    return Fernet(clave.encode())


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token):
    return _fernet().decrypt(token.encode()).decode()
