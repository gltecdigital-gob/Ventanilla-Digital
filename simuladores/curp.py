"""Validación local de la CURP: formato y dígito verificador.

Esto NO sustituye la consulta a RENAPO. Solo evita enviar a RENAPO claves que
no pueden existir (errores de dedo) y sirve mientras se firma el convenio.
"""
import re
from datetime import date

ENTIDADES = (
    "AS|BC|BS|CC|CL|CM|CS|CH|DF|DG|GT|GR|HG|JC|MC|MN|MS|NT|NL|OC|PL|QT|QR|SP|SL|SR|TC|TS|TL|VZ|YN|ZS|NE"
)
PATRON = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}"          # iniciales
    r"(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])"  # fecha de nacimiento AAMMDD
    r"[HMX]"                            # sexo
    rf"({ENTIDADES})"                   # entidad de nacimiento
    r"[B-DF-HJ-NP-TV-Z]{3}"             # consonantes internas
    r"[A-Z\d]"                          # homoclave: dígito (nacidos antes de 2000) o letra
    r"\d$"                              # dígito verificador
)
ALFABETO = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"


def normalizar(curp):
    return (curp or "").strip().upper().replace(" ", "")


def digito_verificador(curp17):
    suma = sum(ALFABETO.index(caracter) * (18 - posicion) for posicion, caracter in enumerate(curp17))
    return (10 - suma % 10) % 10


def fecha_nacimiento(curp):
    """Fecha de nacimiento que codifica la CURP, o None si no es una fecha real."""
    anio, mes, dia = int(curp[4:6]), int(curp[6:8]), int(curp[8:10])
    siglo = 1900 if curp[16].isdigit() else 2000
    try:
        return date(siglo + anio, mes, dia)
    except ValueError:
        return None


def validar_formato(curp):
    """Devuelve (es_valida, motivo). No consulta ningún servicio externo."""
    curp = normalizar(curp)
    if len(curp) != 18:
        return False, "La CURP debe tener 18 caracteres."
    if not PATRON.match(curp):
        return False, "La CURP no tiene el formato correcto."
    nacimiento = fecha_nacimiento(curp)
    if nacimiento is None or nacimiento > date.today():
        return False, "La fecha de nacimiento de la CURP no es válida."
    if digito_verificador(curp[:17]) != int(curp[17]):
        return False, "El dígito verificador no coincide; revisa que esté bien escrita."
    return True, ""
