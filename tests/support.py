"""Utilidades compartidas por las pruebas.

No tocan la base PostgreSQL real: todos los tests usan SQLite temporal o
in-memory mediante ``create_app({...})``.
"""

from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from models import User, db


class CsrfClient(FlaskClient):
    """Cliente de test que añade automáticamente la cabecera CSRF."""

    csrf_token = None

    def open(self, *args, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        if self.csrf_token:
            headers.setdefault("X-CSRF-Token", self.csrf_token)
        kwargs["headers"] = headers
        return super().open(*args, **kwargs)


def create_user(app, email="admin@example.com", password="secret123"):
    user = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email="admin@example.com", password="secret123"):
    """Inicia sesión y actualiza el token CSRF del cliente.

    Siembra primero un token CSRF anónimo en la sesión para poder enviar el
    POST de login (que también está protegido).
    """
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf"
    client.csrf_token = "test-csrf"
    res = client.post(
        "/api/session", json={"email": email, "password": password}
    )
    if res.status_code != 200:
        raise AssertionError("login falló: %s" % res.get_json())
    client.csrf_token = res.get_json()["csrf_token"]
    return res
