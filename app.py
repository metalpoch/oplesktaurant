"""Oplesktaurant - API Flask (sin Blueprints) y servido de frontend estático.

Punto de entrada (con el intérprete del entorno virtual):
    python -m flask --app app db upgrade             # aplica migraciones
    python -m flask --app app create-admin           # crea cuenta de personal
    python -m flask --app app seed-demo-locations    # ubicaciones ficticias
    python -m flask --app app init-db                # crea tablas directo
    python -m flask --app app run                    # arranca el servidor

El frontend (`/`) es una landing pública. El panel administrativo vive en
`/admin` y exige sesión. Las conversaciones de chat no se persisten.
"""

from collections import deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json as _json
import threading
import time

from flask import Flask, Request, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from flask_migrate import Migrate
except ModuleNotFoundError as exc:
    # Diagnóstico explícito: no se instala ningún fallback que oculte la
    # dependencia. Si el módulo ausente no es flask_migrate, se propaga tal cual.
    if not exc.name or exc.name.split(".")[0] != "flask_migrate":
        raise
    raise ModuleNotFoundError(
        "Falta la dependencia 'Flask-Migrate' (paquete 'flask_migrate'), "
        "necesaria para los comandos `db` (migraciones).\n"
        "Causa habitual: ejecutar Flask con un intérprete distinto al del "
        "entorno virtual, p. ej. el `flask` del Python global.\n"
        "Solución: crea/activa el venv e instala requirements con ese mismo "
        "Python, y usa `python -m flask` con ese intérprete:\n"
        "  python3 -m venv .venv\n"
        "  source .venv/bin/activate\n"
        "  python -m pip install -r requirements.txt\n"
        "  python -m flask --app app db upgrade\n"
        "Verifica el intérprete en uso con `python -m pip show Flask-Migrate` "
        "y `which python`. Consulta el README (sección 'Entorno virtual')."
    ) from exc

from sqlalchemy import update

import chat as chat_module
from auth import (
    csrf_required,
    current_user,
    ensure_csrf_token,
    login_required,
    login_user,
    logout_user,
)
from config import Config
from models import (
    TASK_STATUSES,
    Product,
    RestaurantLocation,
    Task,
    User,
    db,
)


# Límite superior compatible con la columna Numeric(12, 3): 9 dígitos enteros
# y 3 decimales.
MAX_QUANTITY = Decimal("999999999.999")


class RateLimiter:
    """Limitador de tasa en memoria, por proceso y por clave (IP).

    Ventana deslizante simple basada en una cola de marcas de tiempo por clave.
    Es *thread-safe* (``threading.Lock``) y poda periódicamente los buckets sin
    actividad para no crecer sin límite. Al vivir en memoria, el límite es por
    proceso: con varios workers el límite efectivo se multiplica, por lo que al
    escalar se necesita un límite compartido (p. ej. en el reverse proxy).
    """

    def __init__(self, limit, window):
        self.limit = int(limit)
        self.window = float(window)
        self._lock = threading.Lock()
        self._hits = {}
        self._last_prune = 0.0

    def allow(self, key, now=None):
        """Registra un acceso y devuelve ``True`` si está dentro del límite."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            if moment - self._last_prune >= self.window:
                self._prune(moment)
                self._last_prune = moment
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits
            cutoff = moment - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(moment)
            return True

    def _prune(self, now):
        """Elimina marcas vencidas y buckets vacíos (bajo lock)."""
        cutoff = now - self.window
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]

    def bucket_count(self):
        """Número de claves con actividad registrada (para comprobaciones)."""
        with self._lock:
            return len(self._hits)


# Ubicaciones ficticias de demostración. Direcciones inventadas sin municipio
# real: son datos ficticios y se marcan como tales (`is_demo`).
DEMO_LOCATIONS = (
    {
        "name": "Oplesktaurant Sucursal Fantasía",
        "address": "Calle de los Sabores Imaginarios 123, Villa Inventada",
        "pos_x": 0.22,
        "pos_y": 0.68,
        "is_demo": True,
    },
    {
        "name": "Oplesktaurant Sucursal Ensueño",
        "address": "Avenida de la Comida Soñada 45, Ciudad Nube",
        "pos_x": 0.55,
        "pos_y": 0.34,
        "is_demo": True,
    },
    {
        "name": "Oplesktaurant Sucursal Quimera",
        "address": "Paseo del Sabor Inexistente 7, Pueblo Espejismo",
        "pos_x": 0.80,
        "pos_y": 0.72,
        "is_demo": True,
    },
)


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _require_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Se espera un cuerpo JSON de tipo objeto.")
    return data


def _clean_str(value, field, required=False, max_length=None):
    if value is None:
        if required:
            raise ValidationError(f"El campo '{field}' es obligatorio.")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"El campo '{field}' debe ser texto.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"El campo '{field}' no puede estar vacío.")
    if max_length and len(value) > max_length:
        raise ValidationError(
            f"El campo '{field}' no puede superar {max_length} caracteres."
        )
    return value or None


def _parse_decimal(value, field, allow_none=True, allow_negative=False):
    """Convierte un valor a Decimal finito, sin redondear."""
    if value is None:
        if allow_none:
            return None
        raise ValidationError(f"El campo '{field}' es obligatorio.")
    if isinstance(value, bool):
        raise ValidationError(f"El campo '{field}' debe ser numérico.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError(f"El campo '{field}' debe ser numérico.")
    if not number.is_finite():
        raise ValidationError(f"El campo '{field}' debe ser un número finito.")
    if not allow_negative and number < 0:
        raise ValidationError(f"El campo '{field}' no puede ser negativo.")
    return number


def _decimal_places(number):
    """Número de decimales significativos (ignora ceros finales)."""
    exponent = number.normalize().as_tuple().exponent
    return -exponent if exponent < 0 else 0


def _validate_quantity(number, field="quantity"):
    """Valida precisión/almacenamiento de Numeric(12, 3) sin redondear."""
    places = _decimal_places(number)
    if places > 3:
        raise ValidationError(
            f"El campo '{field}' no puede tener más de 3 decimales."
        )
    if number > MAX_QUANTITY:
        raise ValidationError(
            f"El campo '{field}' no puede superar {MAX_QUANTITY}."
        )
    return number


def _parse_quantity(value, field="quantity", allow_none=True):
    """Cantidad no negativa apta para Numeric(12, 3)."""
    number = _parse_decimal(value, field, allow_none=allow_none)
    if number is None:
        return None
    return _validate_quantity(number, field)


def _parse_position(value, field):
    """Coordenada normalizada (0.0–1.0) para el mapa estilizado."""
    number = _parse_decimal(value, field, allow_none=False)
    if number < 0 or number > 1:
        raise ValidationError(
            f"El campo '{field}' debe estar entre 0 y 1 (posición normalizada)."
        )
    return float(number)


def _parse_bool(value, field, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValidationError(f"El campo '{field}' debe ser booleano.")


def _valid_status(value):
    if value not in TASK_STATUSES:
        raise ValidationError(
            "El campo 'status' debe ser 'pending' o 'completed'."
        )
    return value


def _get_task_or_404(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        raise NotFoundError("Tarea no encontrada.")
    return task


def _get_product_or_404(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Producto no encontrado.")
    return product


def _get_location_or_404(location_id):
    location = db.session.get(RestaurantLocation, location_id)
    if location is None:
        raise NotFoundError("Ubicación no encontrada.")
    return location


# ---------------------------------------------------------------------------
# Fábrica de la aplicación
# ---------------------------------------------------------------------------

class DecimalJSONProvider(DefaultJSONProvider):
    """Proveedor JSON que serializa ``Decimal`` sin romper las respuestas.

    El API expone las cantidades como números JSON; ``to_dict`` ya las
    convierte a ``float``, pero si algún ``Decimal`` llegara a una respuesta
    se emite como número en lugar de fallar.
    """

    @staticmethod
    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return DefaultJSONProvider.default(obj)


class DecimalRequest(Request):
    """Request que conserva la precisión de los números JSON de entrada.

    Flask parsea por defecto los literales numéricos como ``float``, lo que
    redondea valores como ``1.23400000000000001`` a ``1.234`` antes de que la
    validación de precisión los inspeccione. Aquí se parsea el cuerpo de la
    petición como ``Decimal`` para no perder dígitos.

    La serialización de respuestas y su lectura posterior conservan el
    comportamiento estándar de Flask (números como ``float``), por lo que el
    contrato JSON del API no cambia.
    """

    def get_json(self, force=False, silent=False, cache=True):
        if cache and self._cached_json[silent] is not Ellipsis:
            return self._cached_json[silent]

        if not (force or self.is_json):
            if not silent:
                return self.on_json_loading_failed(None)
            return None

        data = self.get_data(cache=cache)

        try:
            rv = _json.loads(data, parse_float=Decimal)
        except ValueError as e:
            if silent:
                rv = None
                if cache:
                    normal_rv, _ = self._cached_json
                    self._cached_json = (normal_rv, rv)
            else:
                rv = self.on_json_loading_failed(e)
                if cache:
                    _, silent_rv = self._cached_json
                    self._cached_json = (rv, silent_rv)
        else:
            if cache:
                self._cached_json = (rv, rv)

        return rv


def create_app(config_override=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    Config.init_app(app)

    # Parsea el cuerpo JSON de entrada como Decimal para no perder dígitos
    # antes de validar la precisión de Numeric(12, 3). Las respuestas siguen
    # usando el proveedor JSON estándar.
    app.request_class = DecimalRequest
    app.json = DecimalJSONProvider(app)

    if config_override:
        app.config.update(config_override)

    db.init_app(app)

    # Flask-Migrate/Alembic: registra los comandos `flask db ...` y enlaza
    # Alembic con los metadatos de SQLAlchemy. No se conecta a la base de
    # datos ni crea ni altera tablas al importar la app.
    Migrate(app, db)

    _register_frontend(app)
    _register_api(app)
    _register_errors(app)
    _register_cli(app)

    return app


def _register_frontend(app):
    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/login")
    def login_page():
        return send_from_directory(app.static_folder, "login.html")

    @app.route("/admin")
    @login_required
    def admin_page():
        return send_from_directory(app.static_folder, "admin.html")


def _register_api(app):

    # Limitador de tasa del chat público: en memoria y por proceso, por IP.
    # No confía en X-Forwarded-For (falsificable): usa la IP de la conexión.
    chat_limiter = RateLimiter(
        limit=app.config.get("CHAT_RATE_LIMIT"),
        window=app.config.get("CHAT_RATE_WINDOW_SECONDS"),
    )

    # ---- Sesión -----------------------------------------------------------

    @app.route("/api/session", methods=["GET"])
    def get_session():
        token = ensure_csrf_token()
        user = current_user()
        return jsonify(
            {
                "authenticated": user is not None,
                "user": user.to_dict() if user is not None else None,
                "csrf_token": token,
            }
        )

    @app.route("/api/session", methods=["POST"])
    @csrf_required
    def create_session():
        data = _require_json()
        email = _clean_str(data.get("email"), "email", required=True, max_length=255)
        password = data.get("password")
        if not isinstance(password, str) or not password:
            raise ValidationError("El campo 'password' es obligatorio.")
        user = User.query.filter_by(email=email.lower()).first()
        if user is None or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Credenciales inválidas."}), 401
        token = login_user(user)
        return jsonify(
            {
                "authenticated": True,
                "user": user.to_dict(),
                "csrf_token": token,
            }
        )

    @app.route("/api/session", methods=["DELETE"])
    @csrf_required
    def delete_session():
        logout_user()
        token = ensure_csrf_token()
        return jsonify({"authenticated": False, "user": None, "csrf_token": token})

    # ---- Chat -------------------------------------------------------------

    @app.route("/api/chat", methods=["POST"])
    def chat_endpoint():
        client_ip = request.remote_addr or "desconocida"
        if not chat_limiter.allow(client_ip):
            return (
                jsonify(
                    {
                        "error": "Demasiadas solicitudes. Inténtalo de nuevo "
                        "en un minuto."
                    }
                ),
                429,
            )
        data = _require_json()
        context = data.get("context")
        if "context" in data and (
            not isinstance(context, str) or context not in ("public", "admin")
        ):
            return jsonify({"error": "El contexto debe ser public o admin."}), 400
        user = current_user()
        if context == "admin" and user is None:
            return jsonify({"error": "La sesión del panel ha expirado. Inicia sesión de nuevo."}), 401
        # Sin contexto se conserva el contrato anterior basado en la sesión.
        identity = (
            chat_module.MESI if context == "public"
            else chat_module.NBAPEH if user is not None else chat_module.MESI
        )
        try:
            reply = chat_module.generate_reply(
                identity, data.get("message"), data.get("history")
            )
        except chat_module.ChatError as error:
            return jsonify({"error": error.message}), 400
        return jsonify({"identity": identity, "reply": reply})

    # ---- Ubicaciones ------------------------------------------------------

    @app.route("/api/locations", methods=["GET"])
    def list_locations():
        locations = RestaurantLocation.query.order_by(
            RestaurantLocation.id.asc()
        ).all()
        return jsonify([loc.to_dict() for loc in locations])

    @app.route("/api/locations", methods=["POST"])
    @login_required
    @csrf_required
    def create_location():
        data = _require_json()
        address = _clean_str(
            data.get("address"), "address", required=True, max_length=300
        )
        if RestaurantLocation.query.filter_by(address=address).first() is not None:
            raise ValidationError("Ya existe una ubicación con esa dirección.")
        location = RestaurantLocation(
            name=_clean_str(
                data.get("name"), "name", required=True, max_length=200
            ),
            address=address,
            is_demo=_parse_bool(data.get("is_demo"), "is_demo", default=False),
            pos_x=_parse_position(data.get("pos_x"), "pos_x"),
            pos_y=_parse_position(data.get("pos_y"), "pos_y"),
        )
        db.session.add(location)
        db.session.commit()
        return jsonify(location.to_dict()), 201

    @app.route("/api/locations/<int:location_id>", methods=["GET"])
    @login_required
    def get_location(location_id):
        return jsonify(_get_location_or_404(location_id).to_dict())

    @app.route("/api/locations/<int:location_id>", methods=["PATCH", "PUT"])
    @login_required
    @csrf_required
    def update_location(location_id):
        location = _get_location_or_404(location_id)
        data = _require_json()
        if "name" in data:
            location.name = _clean_str(
                data.get("name"), "name", required=True, max_length=200
            )
        if "address" in data:
            new_address = _clean_str(
                data.get("address"), "address", required=True, max_length=300
            )
            duplicate = RestaurantLocation.query.filter(
                RestaurantLocation.address == new_address,
                RestaurantLocation.id != location.id,
            ).first()
            if duplicate is not None:
                raise ValidationError("Ya existe una ubicación con esa dirección.")
            location.address = new_address
        if "is_demo" in data:
            location.is_demo = _parse_bool(data.get("is_demo"), "is_demo")
        if "pos_x" in data:
            location.pos_x = _parse_position(data.get("pos_x"), "pos_x")
        if "pos_y" in data:
            location.pos_y = _parse_position(data.get("pos_y"), "pos_y")
        if not any(
            key in data for key in ("name", "address", "is_demo", "pos_x", "pos_y")
        ):
            raise ValidationError(
                "Debes enviar al menos 'name', 'address', 'is_demo', 'pos_x' "
                "o 'pos_y'."
            )
        db.session.commit()
        return jsonify(location.to_dict())

    @app.route("/api/locations/<int:location_id>", methods=["DELETE"])
    @login_required
    @csrf_required
    def delete_location(location_id):
        location = _get_location_or_404(location_id)
        db.session.delete(location)
        db.session.commit()
        return ("", 204)

    # ---- Tareas -----------------------------------------------------------

    @app.route("/api/tasks", methods=["GET"])
    @login_required
    def list_tasks():
        query = Task.query
        status = request.args.get("status")
        if status is not None:
            _valid_status(status)
            query = query.filter_by(status=status)
        tasks = query.order_by(Task.id.asc()).all()
        return jsonify([t.to_dict() for t in tasks])

    @app.route("/api/tasks", methods=["POST"])
    @login_required
    @csrf_required
    def create_task():
        data = _require_json()
        title = _clean_str(data.get("title"), "title", required=True, max_length=200)
        description = _clean_str(
            data.get("description"), "description", required=False
        )
        task = Task(title=title, description=description, status="pending")
        db.session.add(task)
        db.session.commit()
        return jsonify(task.to_dict()), 201

    @app.route("/api/tasks/<int:task_id>", methods=["GET"])
    @login_required
    def get_task(task_id):
        return jsonify(_get_task_or_404(task_id).to_dict())

    @app.route("/api/tasks/<int:task_id>", methods=["PATCH", "PUT"])
    @login_required
    @csrf_required
    def update_task(task_id):
        task = _get_task_or_404(task_id)
        data = _require_json()
        if "title" in data:
            task.title = _clean_str(
                data.get("title"), "title", required=True, max_length=200
            )
        if "description" in data:
            task.description = _clean_str(
                data.get("description"), "description", required=False
            )
        if "status" in data:
            task.status = _valid_status(data.get("status"))
        if not any(k in data for k in ("title", "description", "status")):
            raise ValidationError(
                "Debes enviar al menos 'title', 'description' o 'status'."
            )
        db.session.commit()
        return jsonify(task.to_dict())

    @app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
    @login_required
    @csrf_required
    def delete_task(task_id):
        task = _get_task_or_404(task_id)
        db.session.delete(task)
        db.session.commit()
        return ("", 204)

    # ---- Productos / inventario ------------------------------------------

    @app.route("/api/products", methods=["GET"])
    @login_required
    def list_products():
        products = Product.query.order_by(Product.id.asc()).all()
        return jsonify([p.to_dict() for p in products])

    @app.route("/api/products", methods=["POST"])
    @login_required
    @csrf_required
    def create_product():
        data = _require_json()
        name = _clean_str(data.get("name"), "name", required=True, max_length=200)
        category = _clean_str(data.get("category"), "category", required=False)
        unit = _clean_str(data.get("unit"), "unit", required=True, max_length=50)
        quantity = _parse_quantity(data.get("quantity"), "quantity", allow_none=True)
        product = Product(
            name=name,
            category=category,
            unit=unit,
            quantity=quantity if quantity is not None else Decimal("0"),
        )
        db.session.add(product)
        db.session.commit()
        return jsonify(product.to_dict()), 201

    @app.route("/api/products/<int:product_id>", methods=["GET"])
    @login_required
    def get_product(product_id):
        return jsonify(_get_product_or_404(product_id).to_dict())

    @app.route("/api/products/<int:product_id>", methods=["PATCH", "PUT"])
    @login_required
    @csrf_required
    def update_product(product_id):
        product = _get_product_or_404(product_id)
        data = _require_json()
        if "name" in data:
            product.name = _clean_str(
                data.get("name"), "name", required=True, max_length=200
            )
        if "category" in data:
            product.category = _clean_str(
                data.get("category"), "category", required=False
            )
        if "unit" in data:
            product.unit = _clean_str(
                data.get("unit"), "unit", required=True, max_length=50
            )
        if "quantity" in data:
            quantity = _parse_quantity(
                data.get("quantity"), "quantity", allow_none=False
            )
            product.quantity = quantity
        if not any(k in data for k in ("name", "category", "unit", "quantity")):
            raise ValidationError(
                "Debes enviar al menos 'name', 'category', 'unit' o 'quantity'."
            )
        db.session.commit()
        return jsonify(product.to_dict())

    @app.route("/api/products/<int:product_id>/quantity", methods=["POST"])
    @login_required
    @csrf_required
    def adjust_product_quantity(product_id):
        _get_product_or_404(product_id)
        data = _require_json()
        if "delta" not in data:
            raise ValidationError("El campo 'delta' es obligatorio para ajustar.")
        delta = _parse_decimal(
            data.get("delta"), "delta", allow_none=False, allow_negative=True
        )
        # El delta también debe respetar la precisión de Numeric(12, 3).
        _validate_quantity(delta, "delta")

        # Actualización atómica en SQL: la condición `quantity + delta >= 0`
        # se evalúa en la base de datos, de modo que no hay read-modify-write
        # y se evita el lost update ante ajustes concurrentes. Funciona en
        # PostgreSQL y SQLite.
        stmt = (
            update(Product)
            .where(
                Product.id == product_id,
                Product.quantity + delta >= 0,
                Product.quantity + delta <= MAX_QUANTITY,
            )
            .values(
                quantity=Product.quantity + delta,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = db.session.execute(stmt)
        if result.rowcount == 0:
            db.session.rollback()
            product = db.session.get(Product, product_id)
            if product is None:
                raise NotFoundError("Producto no encontrado.")
            current = product.quantity if product.quantity is not None else Decimal("0")
            if current + delta < 0:
                raise ValidationError(
                    "El ajuste dejaría la cantidad en existencia por debajo de cero."
                )
            raise ValidationError(
                f"El ajuste superaría la cantidad máxima permitida ({MAX_QUANTITY})."
            )
        db.session.commit()
        product = db.session.get(Product, product_id)
        return jsonify(product.to_dict())

    @app.route("/api/products/<int:product_id>", methods=["DELETE"])
    @login_required
    @csrf_required
    def delete_product(product_id):
        product = _get_product_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        return ("", 204)

    # ---- Dashboard --------------------------------------------------------

    @app.route("/api/dashboard", methods=["GET"])
    @login_required
    def dashboard():
        pending = Task.query.filter_by(status="pending").count()
        completed = Task.query.filter_by(status="completed").count()
        products = Product.query.count()
        locations = RestaurantLocation.query.count()
        # Conteos reales por categoría de producto (sin sumar unidades
        # incompatibles). Categorías vacías se agrupan como "Sin categoría".
        category_rows = (
            db.session.query(Product.category, db.func.count(Product.id))
            .group_by(Product.category)
            .order_by(Product.category.asc())
            .all()
        )
        categories = [
            {"category": category or "Sin categoría", "count": count}
            for category, count in category_rows
        ]
        return jsonify(
            {
                "tasks_pending": pending,
                "tasks_completed": completed,
                "products": products,
                "locations": locations,
                "products_by_category": categories,
            }
        )


def _register_errors(app):
    @app.errorhandler(ValidationError)
    def handle_validation(error):
        return jsonify({"error": error.message}), 400

    @app.errorhandler(NotFoundError)
    def handle_not_found(error):
        return jsonify({"error": error.message}), 404

    @app.errorhandler(404)
    def handle_404(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Recurso no encontrado."}), 404
        return error

    @app.errorhandler(413)
    def handle_413(error):
        if request.path.startswith("/api/"):
            limit_kib = max(1, int(app.config.get("MAX_CONTENT_LENGTH", 0)) // 1024)
            return (
                jsonify(
                    {
                        "error": "El cuerpo de la petición es demasiado grande "
                        "(máximo %d KiB)." % limit_kib
                    }
                ),
                413,
            )
        return error

    @app.errorhandler(405)
    def handle_405(error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Método no permitido."}), 405
        return error


def _register_cli(app):
    import click

    @app.cli.command("init-db")
    def init_db():
        """Crea las tablas en la base de datos configurada."""
        db.create_all()
        click.echo("Tablas creadas correctamente.")

    @app.cli.command("create-admin")
    def create_admin():
        """Crea una cuenta de personal (email/contraseña interactivos).

        No hay auto-registro público. La contraseña se guarda como hash
        Werkzeug; no se usan credenciales por defecto.
        """
        email = click.prompt("Email del administrador").strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise click.ClickException("El email no tiene un formato válido.")
        if User.query.filter_by(email=email).first() is not None:
            raise click.ClickException(
                "Ya existe una cuenta con ese email. No se crea otra."
            )
        password = click.prompt(
            "Contraseña",
            hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 8:
            raise click.ClickException(
                "La contraseña debe tener al menos 8 caracteres."
            )
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()
        click.echo("Cuenta creada para %s." % email)

    @app.cli.command("seed-demo-locations")
    def seed_demo_locations():
        """Carga las 3 ubicaciones ficticias de demostración (opt-in).

        Es idempotente: solo inserta las que faltan (identificadas por
        dirección). No se ejecuta al importar la app ni al migrar.
        """
        inserted = 0
        skipped = 0
        for demo in DEMO_LOCATIONS:
            existing = RestaurantLocation.query.filter_by(
                address=demo["address"]
            ).first()
            if existing is not None:
                skipped += 1
                continue
            db.session.add(RestaurantLocation(**demo))
            inserted += 1
        db.session.commit()
        click.echo(
            "Ubicaciones de demostración: %d insertadas, %d ya existían."
            % (inserted, skipped)
        )


app = create_app()


if __name__ == "__main__":
    # Modo debug apagado por defecto y solo en loopback. Para desarrollo,
    # actívalo de forma explícita con `flask --app app run --debug`.
    app.run(host="127.0.0.1", port=5000, debug=False)
