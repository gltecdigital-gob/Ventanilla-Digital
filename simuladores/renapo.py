"""Simulador del servicio de CURP de RENAPO para desarrollo y pruebas.

El servicio real se obtiene por convenio de coordinación entre cada municipio y
la Secretaría de Gobernación. Mientras llega, este módulo responde con la misma
forma que usará el adaptador real, con datos inventados. Nunca debe usarse en
producción: `consultar` lo impide cuando DEBUG está apagado.
"""
from django.conf import settings

from .curp import fecha_nacimiento, normalizar, validar_formato

# CURP de prueba con comportamientos especiales.
CURP_DADA_DE_BAJA = "BAJA000101HPLXXXA6"
# Toda CURP válida que no sea la de baja se responde con este nombre ficticio.
NOMBRES_PRUEBA = "PERSONA DE PRUEBA"
APELLIDO_PRUEBA = "SIMULADA"


def consultar(curp):
    from ciudadania.renapo import RespuestaCurp

    if not settings.DEBUG and not getattr(settings, "PERMITIR_SIMULADORES", False):
        raise RuntimeError("El simulador de RENAPO no puede usarse en producción.")
    curp = normalizar(curp)
    if curp == CURP_DADA_DE_BAJA:
        return RespuestaCurp(False, curp, motivo="La CURP está dada de baja.", estatus="baja", simulada=True)
    valida, motivo = validar_formato(curp)
    if not valida:
        return RespuestaCurp(False, curp, motivo=motivo, simulada=True)
    return RespuestaCurp(
        encontrada=True,
        curp=curp,
        nombres=NOMBRES_PRUEBA,
        primer_apellido=APELLIDO_PRUEBA,
        segundo_apellido="RENAPO",
        fecha_nacimiento=fecha_nacimiento(curp),
        sexo=curp[10],
        entidad_nacimiento=curp[11:13],
        estatus="vigente",
        simulada=True,
    )
