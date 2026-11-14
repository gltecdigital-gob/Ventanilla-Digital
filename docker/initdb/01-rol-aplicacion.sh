#!/bin/sh
# La imagen oficial de PostgreSQL crea POSTGRES_USER como superusuario, y un superusuario
# se salta la seguridad por fila. La aplicación usa este otro rol, sin esos privilegios.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE plataforma_app LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB;
ALTER DATABASE "${POSTGRES_DB}" OWNER TO plataforma_app;
ALTER SCHEMA public OWNER TO plataforma_app;
SQL
