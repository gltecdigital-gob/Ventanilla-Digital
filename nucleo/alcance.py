"""Alcance de la seguridad por fila de PostgreSQL.

Cada conexión lleva dos variables de sesión que leen las políticas de la base:

- app.alcance = 'plataforma': se ven todas las filas (páginas públicas, ciudadanía,
  administrador de la plataforma y comandos de operación).
- app.alcance = 'municipio' y app.municipio_id = N: solo se ven y escriben las filas
  del municipio N. Lo usa el personal municipal en el panel y la ventanilla.
- Cualquier otro valor (vacío o desconocido): no se ve ninguna fila.

En SQLite (desarrollo) no hay seguridad por fila y estas funciones no hacen nada.
"""
from contextlib import contextmanager

from django.db import connection

PLATAFORMA = "plataforma"
MUNICIPIO = "municipio"


def _es_postgres():
    return connection.vendor == "postgresql"


def fijar(alcance, municipio_id=None):
    if not _es_postgres():
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.alcance', %s, false), set_config('app.municipio_id', %s, false)",
            [alcance, "" if municipio_id is None else str(int(municipio_id))],
        )


def actual():
    if not _es_postgres():
        return None, None
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.alcance', true), current_setting('app.municipio_id', true)")
        return cursor.fetchone()


@contextmanager
def alcance_municipio(municipio_id):
    anterior = actual()
    fijar(MUNICIPIO, municipio_id)
    try:
        yield
    finally:
        if anterior[0] is not None:
            fijar(anterior[0] or PLATAFORMA, anterior[1] or None)


@contextmanager
def alcance_plataforma():
    anterior = actual()
    fijar(PLATAFORMA)
    try:
        yield
    finally:
        if anterior[0] is not None:
            fijar(anterior[0] or PLATAFORMA, anterior[1] or None)


def al_crear_conexion(sender, connection, **kwargs):
    """Toda conexión nueva arranca con alcance de plataforma; el middleware lo restringe por petición."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.alcance', 'plataforma', false), set_config('app.municipio_id', '', false)")
