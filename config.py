"""Configuración de Oplestaurants.

La URI de base de datos y las credenciales se obtienen de variables de
entorno, sin valores secretos embebidos. Se admite
`SQLALCHEMY_DATABASE_URI` (preferida) y `DATABASE_URL` como alternativa.

La clave de sesión (``FLASK_SECRET_KEY``) es necesaria para firmar la cookie de
sesión. Si no está definida, se genera una clave efímera aleatoria para
desarrollo local; en un entorno persistente **debe** definirse explícitamente,
porque una clave efímera cambia en cada arranque e invalida las sesiones.
"""

import os
import secrets
import warnings

from dotenv import load_dotenv

# Carga .env si existe. No imprime ni expone valores.
load_dotenv()

DEFAULT_DB_URI = "postgresql+psycopg://localhost:5432/oplestaurants"

DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Límite del cuerpo de las peticiones (64 KiB): acota el abuso del chat público
# y descarta cuerpos desproporcionados antes de parsearlos. Se puede ajustar
# con la configuración de la app (p. ej. en tests).
DEFAULT_MAX_CONTENT_LENGTH = 64 * 1024

# Rate limit del chat público: 10 peticiones por minuto y por IP. Es un límite
# en memoria y **por proceso** (válido para el MVP); al escalar a varios
# workers/procesos conviene un límite compartido en el reverse proxy.
DEFAULT_CHAT_RATE_LIMIT = 10
DEFAULT_CHAT_RATE_WINDOW_SECONDS = 60.0


def normalize_db_uri(uri):
    """Normaliza esquemas postgres genéricos al driver psycopg (v3)."""
    if not uri:
        return None
    if uri.startswith("postgres://"):
        return "postgresql+psycopg://" + uri[len("postgres://"):]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg://" + uri[len("postgresql://"):]
    return uri


def database_uri():
    """Devuelve la URI configurada o el valor por defecto local."""
    raw = os.environ.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    return normalize_db_uri(raw) or DEFAULT_DB_URI


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def resolve_secret_key():
    """Devuelve ``FLASK_SECRET_KEY`` o una clave efímera si falta.

    La clave efímera solo es válida para desarrollo local en un único proceso;
    no se registra su valor.
    """
    key = os.environ.get("FLASK_SECRET_KEY")
    if key:
        return key
    warnings.warn(
        "FLASK_SECRET_KEY no está definida: se usa una clave efímera aleatoria. "
        "En un entorno persistente define FLASK_SECRET_KEY.",
        RuntimeWarning,
        stacklevel=2,
    )
    return secrets.token_hex(32)


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

    @staticmethod
    def init_app(app):
        app.config["SQLALCHEMY_DATABASE_URI"] = database_uri()
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        app.config["JSON_SORT_KEYS"] = False

        app.config["SECRET_KEY"] = resolve_secret_key()

        # Límite del cuerpo de las peticiones (64 KiB por defecto) y rate limit
        # del chat. Son configurables para tests y ajustes operativos.
        app.config["MAX_CONTENT_LENGTH"] = DEFAULT_MAX_CONTENT_LENGTH
        app.config["CHAT_RATE_LIMIT"] = DEFAULT_CHAT_RATE_LIMIT
        app.config["CHAT_RATE_WINDOW_SECONDS"] = DEFAULT_CHAT_RATE_WINDOW_SECONDS
        # Cookies de sesión endurecidas: no accesibles por JavaScript y
        # SameSite=Lax para mitigar CSRF. `Secure` se activa con
        # FLASK_SESSION_COOKIE_SECURE=1 al servir por HTTPS.
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        app.config["SESSION_COOKIE_SECURE"] = _as_bool(
            os.environ.get("FLASK_SESSION_COOKIE_SECURE")
        )

        # OpenRouter (solo server-side). Nunca se expone al frontend.
        app.config["OPENROUTER_API_KEY"] = os.environ.get("OPENROUTER_API_KEY")
        app.config["OPENROUTER_MODEL"] = os.environ.get("OPENROUTER_MODEL")
        app.config["OPENROUTER_URL"] = os.environ.get(
            "OPENROUTER_URL", DEFAULT_OPENROUTER_URL
        )
        try:
            app.config["OPENROUTER_MAX_TOKENS"] = max(
                256, min(2000, int(os.environ.get("OPENROUTER_MAX_TOKENS", "1200")))
            )
        except (TypeError, ValueError):
            app.config["OPENROUTER_MAX_TOKENS"] = 1200
        try:
            timeout = float(os.environ.get("OPENROUTER_TIMEOUT", "20"))
        except (TypeError, ValueError):
            timeout = 20.0
        app.config["OPENROUTER_TIMEOUT"] = timeout
