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

## Qué NO incluye todavía

- Registro e inicio de sesión de la ciudadanía (Llave MX y cuenta municipal): etapa 2.
- Solicitudes en línea, bandeja de dependencias, firma y código QR: etapa 3.
- Pagos y consultas internas a predial y agua: etapa 4.
- Seguridad por fila en PostgreSQL. Hoy la separación entre municipios se aplica en la aplicación
  y está cubierta por pruebas; el refuerzo en la base de datos se agrega en la etapa 2.
- Segundo factor para servidores públicos: etapa 2.
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
alcance del Enlace, bitácora, regla de publicación y validación de CURP.

## Ambiente con PostgreSQL (Docker)

```bash
cp .env.example .env    # y cambia las claves
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
simuladores/   validación de CURP y simulador de RENAPO
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
