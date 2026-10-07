# Oplestaurants

Cadena de restaurantes (demostración) con una **landing pública** y un
**panel administrativo** para seguimiento de tareas e inventario.

- Backend: Flask (sin Blueprints) + SQLAlchemy (Flask-SQLAlchemy).
- Base de datos: PostgreSQL vía URI por variable de entorno.
- Frontend: HTML, CSS y JavaScript vanilla (sin Jinja ni frameworks) servido por Flask.
- Sesiones Flask firmadas y autenticación por email/contraseña (hash Werkzeug).
- Asistentes de chat: **Mesi** (público) y **Nbapeh** (panel), servidos por el backend.

## Requisitos

- Python 3.10+ (probado con 3.14).
- PostgreSQL (para ejecución real).

### Entorno virtual (recomendado y necesario para las migraciones)

`Flask-Migrate` debe estar instalado en el **mismo intérprete** con el que se
ejecuta la app. Ejecutar el `flask` del Python global (donde quizá no está
`flask_migrate`) provoca:

```text
ModuleNotFoundError: No module named 'flask_migrate'
```

Crea y activa un entorno virtual, e instala las dependencias con ese Python:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Con el entorno activado, `python` y `flask` apuntan a `.venv`. Si prefieres no
activarlo, invoca siempre el intérprete del venv de forma explícita
(`.venv/bin/python -m ...`). No mezcles el `flask` del Python global con el del
venv: si `flask --app app db` falla pero `.venv/bin/flask` funciona, estás
usando el intérprete equivocado.

> Usa **el mismo intérprete** para instalar dependencias, ejecutar la app y las
> migraciones. Todos los comandos de este README se muestran con el venv.

Comprueba el intérprete y el paquete en uso:

```bash
which python
python -m pip show Flask-Migrate
```

## Configuración

1. Copia `.env.example` a `.env` y ajusta los valores locales:

```bash
cp .env.example .env
```

2. Variables admitidas (se lee `.env` sin imprimir secretos):

- `SQLALCHEMY_DATABASE_URI` (preferida). Ejemplo:
  `postgresql+psycopg://usuario:contrasena@localhost:5432/oplestaurants`
- `DATABASE_URL` (alternativa compatible; se usa si la anterior no existe).
  Los esquemas `postgres://` y `postgresql://` se normalizan al driver `psycopg`.
- `FLASK_SECRET_KEY` (**obligatoria en un entorno persistente**). Firma la
  cookie de sesión. Si falta en local, se genera una clave **efímera** aleatoria
  (las sesiones se invalidan en cada arranque).
- `FLASK_SESSION_COOKIE_SECURE` (`1` para servir cookies solo por HTTPS).
- `OPENROUTER_API_KEY` y `OPENROUTER_MODEL`, usadas **solo en el backend** por el
  chat. `OPENROUTER_URL` y `OPENROUTER_TIMEOUT` son opcionales.
- `OPENROUTER_MAX_TOKENS` (opcional, predeterminado 1200; limitado entre 256 y
  2000 para permitir respuestas de modelos con razonamiento sin agotar la salida).

Límites de la aplicación (no secretos, configurables en `create_app`):

- `MAX_CONTENT_LENGTH` (64 KiB por defecto): rechaza con `413` (JSON) los cuerpos
  de petición desproporcionados antes de parsearlos.
- Chat público (`/api/chat`): rate limit de **10 peticiones por minuto y por IP**
  (configurable con `CHAT_RATE_LIMIT` / `CHAT_RATE_WINDOW_SECONDS`). El exceso
  responde `429` (JSON).

Si no se define la URI, se usa por defecto:
`postgresql+psycopg://localhost:5432/oplestaurants`.

> La clave de OpenRouter **nunca** se envía al navegador ni se registra. El
> frontend llama a `/api/chat` y el backend habla con el proveedor.

## Base de datos y migraciones (Flask-Migrate/Alembic)

El esquema versionado vive en `migrations/` y se aplica con Flask-Migrate. Las
tablas **no** se crean al importar la app.

> Todos los comandos de esta sección deben ejecutarse con el intérprete del
> entorno virtual: `python -m flask --app app ...` (o `.venv/bin/python -m
> flask ...`). Así `flask_migrate` está disponible y `flask db` aparece en
> `--help`.

### Esquema nuevo (primera puesta en marcha)

Para una base de datos **nueva**, aplica las migraciones versionadas; esto crea
las tablas (`tasks`, `products`, `users`, `restaurant_locations`) y registra la
revisión en `alembic_version`:

```bash
python -m flask --app app db upgrade
```

No hace falta `db migrate` ni `db stamp` para una base nueva. Para aplicar
migraciones pendientes después de actualizar el código, repite el mismo comando.

> Las ubicaciones ficticias **no** se insertan en la migración. Se cargan de
> forma opt-in con `seed-demo-locations` (ver más abajo).

### Flujo de desarrollo

1. Genera una revisión a partir de los modelos (no modifica el esquema):

   ```bash
   python -m flask --app app db migrate -m "descripción del cambio"
   ```

2. Revisa siempre el script generado en `migrations/versions/` antes de
   aplicarlo: confirma columnas, tipos, `CHECK` constraints e índices, y que
   `upgrade()`/`downgrade()` sean coherentes.

3. Aplica las migraciones pendientes:

   ```bash
   python -m flask --app app db upgrade
   ```

### Base de datos existente creada con `init-db`

No asumas que una base ya creada coincide con la revisión base y **no la marques
automáticamente**. Verifica el esquema real (por ejemplo con `psql` y
`\d tasks`, sin volcar la contraseña) y, solo si coincide **exactamente**, marca
la revisión con `python -m flask --app app db stamp head`. Haz respaldo antes de
cualquier operación sobre una base con datos.

## Cuentas de personal (sin auto-registro)

No hay registro público. Crea la cuenta inicial de forma interactiva (email y
contraseña, con confirmación; la contraseña se guarda como hash Werkzeug):

```bash
python -m flask --app app create-admin
```

- El comando valida el formato del email y exige una contraseña de al menos 8
  caracteres.
- No se usan credenciales por defecto ni semillas de contraseñas.
- La contraseña se escribe de forma oculta y no se muestra ni se registra.

El login es por sesión. La página `/login` inicia sesión y `/admin` queda
protegido. La cookie de sesión es `httpOnly` y `SameSite=Lax`, y se puede forzar
`Secure` con `FLASK_SESSION_COOKIE_SECURE=1`.

## Ubicaciones de demostración (datos ficticios)

El mapa de la landing usa posiciones **normalizadas** `x`/`y` (0–1), no
coordenadas geográficas. Las tres ubicaciones de ejemplo son **datos ficticios
de demostración** (calles inventadas, marcadas con `is_demo`):

```bash
python -m flask --app app seed-demo-locations
```

- Es **idempotente**: solo inserta las que faltan (identificadas por dirección).
- Es **opt-in**: no se ejecuta al importar la app ni al migrar.
- Sin seed, la landing muestra un **empty state** y el listado vacío.

## Ejecutar

Con el entorno virtual activado (o usando `.venv/bin/python`):

```bash
python -m flask --app app run
# o
python app.py
```

- Landing pública: `http://127.0.0.1:5000/`
- Login del personal: `http://127.0.0.1:5000/login`
- Panel administrativo: `http://127.0.0.1:5000/admin`

El servidor escucha solo en `127.0.0.1` y el **modo debug está apagado por
defecto**. Para desarrollo local puedes activarlo explícitamente; nunca lo
actives en un entorno accesible por terceros:

```bash
python -m flask --app app run --debug
```

## Docker y publicación en GHCR

Construcción local:

```bash
docker build -t oplestaurants:local .
docker run --rm --env-file .env -p 5000:5000 oplestaurants:local
```

El `.dockerignore` excluye `.env` y archivos locales; las credenciales solo se
inyectan en runtime. La imagen corre Gunicorn como usuario no-root. Configura
`FLASK_SECRET_KEY` en `.env` antes de iniciarla.

Las migraciones **no** se ejecutan al arrancar el servidor. Antes de desplegar
una versión que requiera cambios de esquema, ejecuta el upgrade como tarea
one-shot usando exactamente la misma imagen y configuración:

```bash
docker run --rm --env-file .env ghcr.io/OWNER/REPO:TAG \
  python -m flask --app app db upgrade
```

El comando termina al aplicar la migración; luego inicia el contenedor normal.
Para crear el usuario inicial, también puedes ejecutar `create-admin` con un
contenedor interactivo y la misma configuración.

`.github/workflows/container.yml` corre tests, chequeos Python/JavaScript y
construye la imagen tanto en `push` como en `pull_request`. Publica en
`ghcr.io/<owner>/<repo>` con tags de rama, tag Git, SHA y `latest` en la rama
default; un PR del mismo repositorio publica además `pr-<n>`. Los PRs de forks
construyen y validan, pero **no publican**: GitHub no concede `packages: write` a
ese token de manera segura. Se usa `GITHUB_TOKEN`, sin secretos manuales. Los
paquetes GHCR nuevos pueden quedar privados; cambia la visibilidad desde los
ajustes del paquete si quieres permitir `docker pull` público.

## API

Públicas (solo lectura / chat):

| Método | Ruta | Descripción |
| ------ | ---- | ----------- |
| GET | `/` | Landing pública. |
| GET | `/login` | Página de acceso. |
| GET | `/api/locations` | Lista de ubicaciones (pública, solo lectura). |
| GET | `/api/session` | Estado de sesión + `csrf_token` para el frontend. |
| POST | `/api/session` | Login (requiere cabecera `X-CSRF-Token`). |
| DELETE | `/api/session` | Logout (requiere `X-CSRF-Token`). |
| POST | `/api/chat` | Chat: Mesi si no hay sesión, Nbapeh si la hay. Rate limit por IP (`429`). |

Administrativas (requieren sesión; las que modifican estado requieren además
`X-CSRF-Token`):

| Método | Ruta | Descripción |
| ------ | ---- | ----------- |
| GET | `/api/tasks` | Lista tareas. Filtro opcional `?status=pending\|completed`. |
| POST | `/api/tasks` | Crea tarea (`title` obligatorio, `description` opcional). |
| PATCH/PUT/DELETE | `/api/tasks/<id>` | Actualiza o elimina una tarea. |
| GET | `/api/products` | Lista productos. |
| POST | `/api/products` | Crea producto (`name` y `unit` obligatorios; `quantity` >= 0). |
| PATCH/PUT/DELETE | `/api/products/<id>` | Edita o elimina un producto. |
| POST | `/api/products/<id>/quantity` | Ajusta cantidad con `{"delta": numero}`. |
| GET/POST | `/api/locations` | Lista (pública) o crea ubicación (admin). |
| GET/PATCH/PUT/DELETE | `/api/locations/<id>` | Gestiona una ubicación (admin). |
| GET | `/api/dashboard` | Conteos reales y desglose por categoría. |

`quantity` y `delta` corresponden a `Numeric(12, 3)`: se rechazan (HTTP 400) los
valores con **más de 3 decimales** (sin redondeo silencioso) y los que superan
**999999999.999**. El ajuste de cantidad usa una actualización atómica en SQL
(`quantity + delta >= 0` evaluada en la base de datos), seguro ante peticiones
concurrentes.

### CSRF

Las operaciones que modifican estado exigen la cabecera `X-CSRF-Token` con el
token ligado a la sesión. El frontend lo obtiene de `GET /api/session` (y de la
respuesta del login). Sin token válido se responde `403`.

## Asistentes de chat

- **Mesi**: asistente público de la landing. Carismático y orientado a atraer
  clientes. Cada oración termina literalmente con `que mira bobo`; además del
  prompt, un postprocesado determinista garantiza el sufijo aunque el modelo lo
  omita.
- **Nbapeh**: dentro del panel autenticado, ayudante de uso de la plataforma.

Ambos hablan solo de Oplestaurants, no inventan sucursales/promociones/precios y
no ejecutan acciones ni generan código. La llamada a OpenRouter ocurre **solo en
el backend** (librería estándar), con timeout y límites de longitud/contexto, sin
persistir conversaciones ni usar herramientas. Si falta configuración o el
proveedor falla, se devuelve un mensaje neutral que no revela la configuración.

El chat público está protegido con un rate limit **en memoria y por proceso**:
10 peticiones por minuto y por IP de conexión (no se confía en
`X-Forwarded-For`, que es falsificable). Se limpian periódicamente los buckets
inactivos para no crecer sin límite. Es apropiado para el MVP de un solo
proceso; **al escalar a varios workers/procesos** el límite efectivo se
multiplica, por lo que se requerirá un límite compartido en el reverse proxy (o
un almacén externo). El cuerpo de las peticiones se limita a `MAX_CONTENT_LENGTH`
(64 KiB) y el exceso se responde con `413`/`429` en JSON.

## Pruebas

Los tests usan SQLite in-memory o un archivo SQLite temporal mediante
configuración de test; **nunca** tocan la base PostgreSQL por defecto. Incluyen
pruebas aisladas de migraciones (`tests/test_migrations.py`) que aplican
`upgrade head` y `downgrade base` solo contra SQLite. No requieren pytest.

Las pruebas de las funciones puras del frontend (resolución segura del `next`
del login y avisos de datos ficticios) se ejecutan con Node si está disponible;
si no lo está, se omiten automáticamente.

```bash
python -m unittest discover -s tests -v
```

Comprobación de sintaxis:

```bash
python -m py_compile app.py config.py models.py auth.py chat.py \
    tests/test_api.py tests/test_auth.py tests/test_chat.py \
    tests/test_config.py tests/test_frontend.py tests/test_locations.py \
    tests/test_migrations.py tests/support.py
node --check static/js/chat.js
node --check static/js/landing.js
node --check static/js/admin.js
node --check static/js/auth.js
```

## Estructura

```
.
├── app.py              # Fábrica de la app, rutas, servido estático y CLI
├── config.py           # .env, URI de DB, clave de sesión y OpenRouter
├── models.py           # Task, Product, User y RestaurantLocation + db
├── auth.py             # Sesión, login requerido y CSRF
├── chat.py             # Mesi/Nbapeh y llamada a OpenRouter (backend)
├── requirements.txt
├── .env.example
├── Dockerfile
├── .dockerignore
├── .github/workflows/container.yml
├── migrations/         # Repositorio Alembic (env.py, alembic.ini, versions/)
│   └── versions/
│       ├── ..._initial_schema_tasks_and_products.py
│       └── ..._add_users_and_restaurant_locations.py
├── static/
│   ├── index.html      # Landing pública (mapa + Mesi)
│   ├── login.html      # Acceso del personal
│   ├── admin.html      # Panel (dashboard + CRUD + Nbapeh)
│   ├── css/{style,landing,admin}.css
│   └── js/{chat,landing,auth,admin}.js
└── tests/
    ├── test_api.py
    ├── test_auth.py
    ├── test_chat.py
    ├── test_config.py
    ├── test_frontend.py
    ├── test_locations.py
    ├── test_migrations.py
    └── support.py
```

## Fuera de alcance (MVP)

Sin auto-registro público. El chat no ejecuta acciones ni modifica registros.
El mapa usa posiciones normalizadas (no geográficas) y las ubicaciones de
demostración son ficticias. No se inventan umbrales de stock, ventas, ingresos
ni métricas no derivadas de datos reales.
