"""Adaptador del servicio de CURP de RENAPO.

El resto de la plataforma solo llama a `consultar_curp`. Qué servicio responde se
elige con la variable RENAPO_BACKEND:

- "simulador": datos inventados, solo para desarrollo y pruebas.
- "convenio": servicio web real de RENAPO. Se implementa cuando cada municipio firme
  su convenio de coordinación con la Secretaría de Gobernación y RENAPO entregue la
  especificación técnica y la credencial.
"""
from dataclasses import dataclass
from datetime import date

from django.conf import settings


class ServicioNoDisponible(Exception):
    """RENAPO no respondió o no está configurado; no significa que la CURP no exista."""


@dataclass(frozen=True)
class RespuestaCurp:
    encontrada: bool
    curp: str
    motivo: str = ""
    nombres: str = ""
    primer_apellido: str = ""
    segundo_apellido: str = ""
    fecha_nacimiento: date | None = None
    sexo: str = ""
    entidad_nacimiento: str = ""
    estatus: str = ""
    simulada: bool = False


def consultar_curp(curp, municipio=None):
    backend = getattr(settings, "RENAPO_BACKEND", "simulador")
    if backend == "simulador":
        from simuladores import renapo

        return renapo.consultar(curp)
    if backend == "convenio":
        raise ServicioNoDisponible(
            "La conexión con RENAPO aún no está configurada: requiere el convenio del municipio "
            "con la Secretaría de Gobernación y la especificación técnica del servicio."
        )
    raise ServicioNoDisponible(f"RENAPO_BACKEND desconocido: {backend!r}")
