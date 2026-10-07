"""Pruebas de configuración segura (clave de sesión y cookies)."""

import os
import unittest
import warnings
from unittest import mock

from app import create_app
from config import resolve_secret_key


class ConfigTestCase(unittest.TestCase):
    def test_secret_key_desde_entorno(self):
        with mock.patch.dict(os.environ, {"FLASK_SECRET_KEY": "clave-secreta"}):
            self.assertEqual(resolve_secret_key(), "clave-secreta")

    def test_secret_key_efimera_si_falta(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                key = resolve_secret_key()
        self.assertTrue(key)
        self.assertTrue(any(issubclass(w.category, RuntimeWarning) for w in caught))

    def test_config_de_cookies(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            }
        )
        self.assertEqual(app.config["SECRET_KEY"], "test-secret")
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_override_secret_key(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "otra-clave",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            }
        )
        self.assertEqual(app.config["SECRET_KEY"], "otra-clave")


if __name__ == "__main__":
    unittest.main()
