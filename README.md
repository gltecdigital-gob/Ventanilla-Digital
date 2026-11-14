# Plataforma Municipal de Trámites Digitales

Plataforma compartida por varios ayuntamientos para publicar, simplificar y digitalizar
sus trámites conforme a la Ley Nacional para Eliminar Trámites Burocráticos (LNETB).
Piloto: Zacatlán y Huauchinango, Puebla.

## Qué incluye esta entrega (etapa 1)

| Parte | Qué hace |
| --- | --- |
| Catálogo público | Buscador de trámites por municipio, con filtros por dependencia y canal, y ficha de cada trámite. Sin JavaScript ni recursos externos: carga con conexión lenta. |
| Panel de administración (`/panel/`) | Alta y edición de trámites, requisitos, dependencias y servidores públicos. |
| Separación por municipio | Cada usuario solo ve y edita lo de su ayuntamiento; un Enlace solo ve los trámites de su dependencia. |
| Regla de publicación | Una ficha no se puede publicar sin descripción, fundamento, plazo, costo, oficinas y contacto. |
| Bitácora | Registro de altas, cambios, bajas, publicaciones e inicios de sesión. Solo se agrega: no se edita ni se borra. |
| Inventario del piloto | 90 trámites de Zacatlán y 112 de Huauchinango, clasificados por ruta de digitalización (A a D). |
| Simulador de RENAPO | Validación local de formato y dígito verificador de la CURP y respuestas simuladas, para desarrollar la etapa 2 mientras se firma el convenio. |

## Etapa 2: identidad de la ciudadanía

| Parte | Qué hace |
| --- | --- |
| Perfil único por CURP | Una persona, un perfil para todos los municipios (art. 59 LNETB). Los datos vienen de RENAPO y no se editan. |
| Cuenta municipal (`/cuenta/registro/`) | CURP → validación en RENAPO → confirmación del nombre → correo o celular con código → aviso de privacidad. Sin contraseñas: cada acceso pide un código de 6 dígitos. |
| Llave MX (`/cuenta/llave-mx/`) | Ida y vuelta con estado anti-falsificación. Si la CURP ya tenía cuenta municipal, se vinculan en un solo perfil. |
| Niveles de confianza | 1 Básico (cuenta municipal), 2 Verificado (Llave MX o verificación en ventanilla), 3 Alto (Llave MX Verificada). La cuenta municipal nunca pasa de nivel 2 en una sesión. `requiere_nivel(n)` protege las vistas de trámites de la etapa 3. |
| Ventanilla asistida (`/ventanilla/`) | El personal registra o verifica en persona: anota tipo de identificación y solo sus últimos 4 caracteres; confirma el contacto con un código que la persona le dicta. |
| Protección | Límites de intentos por CURP y por IP, códigos de un solo uso guardados como huella, 5 intentos por código, vigencia de 10 minutos, cambio de sesión al entrar, respuesta neutra al pedir código para no revelar qué CURP tienen cuenta, aviso al titular al registrar, vincular o verificar. |
| Transparencia para la persona | En «Mi cuenta» ve cada acceso y cada consulta de sus datos por personal municipal. |
| Simuladores | RENAPO, Llave MX y buzón de correos y mensajes (`/simuladores/buzon/`), solo con `DEBUG` o `PERMITIR_SIMULADORES`. La aplicación no arranca en producción si algún servicio quedó en simulador. |

### Probar la etapa 2 en tu computadora

1. `python manage.py cargar_piloto` (crea también el grupo «Ventanilla»).
2. Registro: entra a `/cuenta/registro/` con una CURP de formato válido, por ejemplo `PEPJ900101HPLRRN02`.
   El simulador de RENAPO responde con el nombre **Persona de prueba** y el apellido **Simulada**.
3. El código llega al buzón de pruebas: `/simuladores/buzon/`.
4. Ventanilla: crea en el panel un servidor público con rol «Personal de ventanilla», marca «Es staff»,
   asígnale municipio y agrégalo al grupo «Ventanilla». Después entra a `/ventanilla/`.
5. Llave MX: `/cuenta/llave-mx/` abre el simulador; marca «Verificada» para probar el nivel 3.
6. CURP de prueba dada de baja: `BAJA000101HPLXXXA6`.

### Lo que depende de terceros

- **RENAPO real** (`RENAPO_BACKEND=convenio`): requiere el convenio de cada municipio con la Secretaría de
  Gobernación y la especificación del servicio. Hoy responde «no podemos validar tu CURP» con un mensaje claro.
- **Llave MX real** (`LLAVE_MX_BACKEND=atdt`): requiere la aprobación y el manual técnico de la ATDT.
- **Mensajes de texto** (`SMS_BACKEND`): requiere contratar un proveedor.
- **Correo**: SMTP del municipio con las variables `EMAIL_*`.

## Seguridad por fila y segundo factor

### Seguridad por fila (PostgreSQL)

La base de datos misma separa los municipios. Aunque una vista del panel olvide filtrar,
PostgreSQL no entrega ni deja escribir filas de otro municipio.

| Quién | Dónde | Qué ve la base |
| --- | --- | --- |
| Personal municipal | `/panel/` y `/ventanilla/` | Solo las filas de su municipio |
| Administrador de la plataforma | En todo el sitio | Todo |
| Ciudadanía y visitantes | Catálogo y «Mi cuenta» | Todo; cada vista filtra por municipio o por persona |
| Comandos (`cargar_piloto`, `shell`) | Fuera de peticiones | Todo |

Tablas protegidas: municipios, dependencias, trámites, requisitos, bitácora y verificaciones presenciales.
Las personas (perfil por CURP) son comunes a todos los municipios y no se separan.

Condiciones para que funcione:

- **El rol con que se conecta la aplicación no puede ser superusuario ni tener `BYPASSRLS`**: esos roles se
  saltan la seguridad por fila. `python manage.py check --deploy` falla (`nucleo.E003`) si es así.
  `docker-compose.yml` ya crea un rol `plataforma_app` sin privilegios.
- **No usar un agrupador de conexiones en modo transacción** (por ejemplo PgBouncer `pool_mode=transaction`):
  el alcance se guarda en la sesión de la conexión.
- En SQLite (desarrollo) no hay seguridad por fila; la separación queda solo en la aplicación.

### Segundo factor para el personal

Todo servidor público necesita, además de su contraseña, un código de una aplicación de autenticación
(Google Authenticator, Microsoft Authenticator, FreeOTP) para entrar al panel o a la ventanilla.

- La primera vez, la plataforma muestra un código QR y entrega 10 códigos de respaldo que se ven una sola vez.
- Cada inicio de sesión pide el código. Un código no se acepta dos veces.
- Cinco intentos fallidos bloquean 15 minutos; cada intento fallido queda en la bitácora.
- Si alguien pierde su teléfono, la Autoridad Municipal (o el administrador) usa la acción
  «Reiniciar segundo factor» en «Servidores públicos»; la sesión abierta de esa persona deja de valer.
- La semilla de cada teléfono se guarda cifrada con `CLAVE_CIFRADO`, distinta de `SECRET_KEY`. Respáldala:
  si se pierde, todo el personal tendrá que configurar su segundo factor de nuevo.
- `SEGUNDO_FACTOR_OBLIGATORIO=0` lo desactiva (solo para desarrollo).

### Pruebas con PostgreSQL

Las pruebas de seguridad por fila solo corren con PostgreSQL y un rol sin privilegios:

```bash
createuser --createdb --no-superuser plataforma   # o con psql: CREATE ROLE ... NOSUPERUSER NOBYPASSRLS CREATEDB
DEBUG=1 DATABASE_URL=postgres://plataforma:clave@localhost:5432/plataforma python manage.py test
```

## Qué NO incluye todavía

- Solicitudes en línea, bandeja de dependencias, firma y código QR: etapa 3.
- Pagos y consultas internas a predial y agua: etapa 4.
- Seguridad por fila en la tabla de servidores públicos: la separación de usuarios entre municipios
  sigue solo en la aplicación (la tabla se usa para identificar al usuario antes de fijar el alcance).
- Personas morales, representación de terceros y personas extranjeras sin CURP: etapa 3.
- Las fichas cargadas solo tienen clave, nombre, dependencia y ruta. Requisitos, costos y plazos
  los captura cada Enlace; hasta entonces el catálogo las marca como «Ficha en levantamiento».

## Cómo ejecutarla en tu computadora

Necesitas Python 3.12 o más reciente.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DEBUG=1                      # solo en desarrollo
python manage.py migrate
python manage.py cargar_piloto      # municipios, dependencias, trámites y grupos de permisos
python manage.py createsuperuser    # administrador de la plataforma
python manage.py runserver
```

Al entrar al panel te pedirá configurar tu segundo factor con una aplicación de autenticación.

```bash
```

- Catálogo: http://127.0.0.1:8000/
- Panel: http://127.0.0.1:8000/panel/

### Dar de alta a la Autoridad Municipal y a los Enlaces

En el panel, sección «Servidores públicos»: crea el usuario, marca «Es staff», elige municipio,
rol y, para un Enlace, su dependencia; después agrégalo al grupo que le corresponde
(«Autoridad Municipal», «Enlace de dependencia» o «Solo consulta»).

## Pruebas

```bash
DEBUG=1 python manage.py test
```

Cubren: carga del piloto, separación entre municipios en el panel y en el catálogo,
alcance del Enlace, bitácora, regla de publicación, validación de CURP, registro y acceso
de la ciudadanía, Llave MX, niveles de confianza, ventanilla asistida y límites de intentos.

## Ambiente con PostgreSQL (Docker)

```bash
cp .env.example .env    # y cambia las claves, incluida CLAVE_CIFRADO
docker compose up --build
docker compose exec web python manage.py cargar_piloto
docker compose exec web python manage.py createsuperuser
```

## Estructura

```
config/        configuración, direcciones y arranque
nucleo/        municipios, dependencias, bitácora y base del panel
cuentas/       servidores públicos y roles
catalogo/      trámites, requisitos, páginas públicas
ciudadania/    perfil por CURP, cuenta municipal, Llave MX, niveles de confianza y ventanilla asistida
simuladores/   validación de CURP y simuladores de RENAPO, Llave MX, correo y mensajes
datos/         inventario del piloto (clave|dependencia|nombre|ruta)
templates/ static/   plantilla base y hoja de estilos
```

## Antes de producción

- `DEBUG=0`, `SECRET_KEY` propia, `ALLOWED_HOSTS` y HTTPS obligatorio.
- PostgreSQL con respaldos diarios y prueba de recuperación.
- Alojamiento en infraestructura pública (art. 60 LNETB).
- Prueba de seguridad por un tercero.
- Revisión y aprobación de cada cambio por la persona técnica responsable de producción.

## Licencia

Por definir con el área jurídica. La LNETB (arts. 91 a 94) pide compartir el código de las
soluciones de digitalización y preferir software libre.
