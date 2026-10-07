"""Autenticación por sesión y protección CSRF para Oplestaurants.

Sin auto-registro público: las cuentas se crean con el comando
``create-admin`` y la contraseña se guarda como hash Werkzeug.

El token CSRF vive en la sesión firmada y se exige en la cabecera
``X-CSRF-Token`` de las operaciones que modifican estado. El frontend vanilla
lo obtiene de ``GET /api/session``.
"""

import hmac
import functools
import secrets

from flask import jsonify, redirect, request, session, url_for

from models import User, db

CSRF_SESSION_KEY = "csrf_token"
USER_SESSION_KEY = "user_id"

CSRF_HEADER = "X-CSRF-Token"


def ensure_csrf_token():
    """Devuelve el token CSRF de la sesión, creándolo si aún no existe."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token():
    """Genera y guarda un token CSRF nuevo (tras login/logout)."""
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def csrf_token_is_valid():
    """Comprueba la cabecera CSRF contra el token de la sesión."""
    expected = session.get(CSRF_SESSION_KEY)
    provided = request.headers.get(CSRF_HEADER)
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(expected), str(provided))


def current_user():
    """Devuelve el ``User`` de la sesión o ``None`` si no hay sesión válida."""
    user_id = session.get(USER_SESSION_KEY)
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_user(user):
    """Inicia sesión rotando el token CSRF tras fijar la identidad."""
    session[USER_SESSION_KEY] = user.id
    return rotate_csrf_token()


def logout_user():
    """Cierra la sesión eliminando identidad y token CSRF."""
    session.pop(USER_SESSION_KEY, None)
    session.pop(CSRF_SESSION_KEY, None)


def login_required(view):
    """Protege una vista: 401 JSON para API, redirección a login para páginas."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if session.get(USER_SESSION_KEY) is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Autenticación requerida."}), 401
            return redirect(url_for("login_page", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def csrf_required(view):
    """Exige un token CSRF válido (cabecera ``X-CSRF-Token``)."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not csrf_token_is_valid():
            return jsonify({"error": "Token CSRF inválido o ausente."}), 403
        return view(*args, **kwargs)

    return wrapped
