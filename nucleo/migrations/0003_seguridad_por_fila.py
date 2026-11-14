"""Seguridad por fila en PostgreSQL: separa en la base los datos de cada municipio.

FORCE ROW LEVEL SECURITY hace que la regla aplique también al dueño de las tablas
(el rol de la aplicación). Solo un superusuario o un rol con BYPASSRLS la saltan;
la verificación `manage.py check --deploy` avisa si la aplicación usa uno así.
En SQLite esta migración no hace nada.
"""
from django.db import migrations

FUNCION = """
CREATE OR REPLACE FUNCTION app_alcance_permite(municipio bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT CASE current_setting('app.alcance', true)
    WHEN 'plataforma' THEN true
    WHEN 'municipio' THEN municipio IS NOT DISTINCT FROM NULLIF(current_setting('app.municipio_id', true), '')::bigint
                          AND NULLIF(current_setting('app.municipio_id', true), '') IS NOT NULL
    ELSE false
  END
$$;
"""

# tabla -> expresión que decide si la fila es visible y escribible
TABLAS = {
    "nucleo_municipio": "app_alcance_permite(id)",
    "nucleo_dependencia": "app_alcance_permite(municipio_id)",
    "catalogo_tramite": "app_alcance_permite(municipio_id)",
    "catalogo_requisito": "EXISTS (SELECT 1 FROM catalogo_tramite t WHERE t.id = tramite_id)",
    "nucleo_eventobitacora": "app_alcance_permite(municipio_id)",
    "ciudadania_verificacionpresencial": "app_alcance_permite(municipio_id)",
}


def activar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(FUNCION)
    for tabla, expresion in TABLAS.items():
        schema_editor.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"DROP POLICY IF EXISTS aislamiento_municipal ON {tabla}")
        schema_editor.execute(
            f"CREATE POLICY aislamiento_municipal ON {tabla} USING ({expresion}) WITH CHECK ({expresion})"
        )


def desactivar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for tabla in TABLAS:
        schema_editor.execute(f"DROP POLICY IF EXISTS aislamiento_municipal ON {tabla}")
        schema_editor.execute(f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")
    schema_editor.execute("DROP FUNCTION IF EXISTS app_alcance_permite(bigint)")


class Migration(migrations.Migration):
    dependencies = [
        ("nucleo", "0002_eventobitacora_persona_alter_eventobitacora_accion_and_more"),
        ("catalogo", "0002_initial"),
        ("ciudadania", "0001_initial"),
    ]
    operations = [migrations.RunPython(activar, desactivar)]
