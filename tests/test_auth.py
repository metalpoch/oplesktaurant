"""Pruebas de autenticación, sesión y CSRF."""

import unittest

from werkzeug.security import check_password_hash

from app import create_app
from models import User, db
from support import CsrfClient, create_user


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            }
        )
        self.app.test_client_class = CsrfClient
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        create_user(self.app, email="admin@example.com", password="secret123")
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def _seed_csrf(self):
        with self.client.session_transaction() as sess:
            sess["csrf_token"] = "csrf-1"
        self.client.csrf_token = "csrf-1"

    def test_sesion_anonima_expone_token_csrf(self):
        res = self.client.get("/api/session")
        body = res.get_json()
        self.assertFalse(body["authenticated"])
        self.assertIsNone(body["user"])
        self.assertTrue(body["csrf_token"])

    def test_login_correcto_y_cierre_de_sesion(self):
        self._seed_csrf()
        res = self.client.post(
            "/api/session",
            json={"email": "admin@example.com", "password": "secret123"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["email"], "admin@example.com")
        self.client.csrf_token = body["csrf_token"]

        # Acceso al panel tras iniciar sesión.
        admin_res = self.client.get("/admin")
        try:
            self.assertEqual(admin_res.status_code, 200)
        finally:
            admin_res.close()

        # Logout.
        out = self.client.delete("/api/session")
        self.assertEqual(out.status_code, 200)
        self.assertFalse(out.get_json()["authenticated"])
        redir = self.client.get("/admin")
        try:
            self.assertEqual(redir.status_code, 302)
        finally:
            redir.close()

    def test_login_credenciales_invalidas(self):
        self._seed_csrf()
        res = self.client.post(
            "/api/session",
            json={"email": "admin@example.com", "password": "incorrecta"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("error", res.get_json())

    def test_login_sin_csrf_falla(self):
        res = self.client.post(
            "/api/session",
            json={"email": "admin@example.com", "password": "secret123"},
        )
        self.assertEqual(res.status_code, 403)

    def test_crear_tarea_sin_csrf_falla(self):
        self._seed_csrf()
        self.client.post(
            "/api/session",
            json={"email": "admin@example.com", "password": "secret123"},
        )
        # Cliente con token válido de sesión pero sin enviar cabecera.
        self.client.csrf_token = None
        res = self.client.post("/api/tasks", json={"title": "T"})
        self.assertEqual(res.status_code, 403)

    def test_api_admin_protegida(self):
        for path in ("/api/tasks", "/api/products", "/api/dashboard"):
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_create_admin_guarda_hash_y_no_texto_plano(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["create-admin"],
            input="nuevo@example.com\nsupersecret\nsupersecret\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        user = User.query.filter_by(email="nuevo@example.com").first()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password_hash, "supersecret")
        self.assertTrue(check_password_hash(user.password_hash, "supersecret"))

    def test_create_admin_no_duplica(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["create-admin"],
            input="admin@example.com\nsupersecret\nsupersecret\n",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(User.query.count(), 1)

    def test_create_admin_rechaza_password_corta(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["create-admin"],
            input="corto@example.com\nabc\nabc\n",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIsNone(User.query.filter_by(email="corto@example.com").first())


if __name__ == "__main__":
    unittest.main()
