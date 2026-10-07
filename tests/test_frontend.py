"""Pruebas del frontend público y del panel.

Verifican estructura accesible, ausencia de credenciales y el comportamiento
de acceso (la landing es pública; el panel exige sesión).

Ejecutar con:

    python3 -m unittest discover -s tests -v
"""

import json
import os
import shutil
import subprocess
import unittest

from app import create_app
from models import db

JS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js"
)
NODE = shutil.which("node")


def run_node_module(module_name, expression):
    """Carga un módulo JS (Node) y evalúa ``expression`` sobre ``mod``.

    Devuelve el resultado decodificado desde JSON. Se usa para probar las
    funciones puras extraídas de los scripts del frontend.
    """
    script = (
        "const mod = require(%s);"
        "process.stdout.write(JSON.stringify(%s));"
        % (json.dumps(os.path.join(JS_DIR, module_name)), expression)
    )
    proc = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError("node falló: %s" % proc.stderr)
    return json.loads(proc.stdout)


class FrontendTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
            }
        )
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def _get_text(self, path):
        res = self.client.get(path)
        try:
            return res.status_code, res.get_data(as_text=True)
        finally:
            res.close()

    # ---- Landing pública --------------------------------------------------

    def test_index_es_landing_publica(self):
        status, html = self._get_text("/")
        self.assertEqual(status, 200)
        self.assertIn("Oplestaurants", html)
        self.assertIn("map-pins", html)
        self.assertIn("Datos ficticios de demostración", html)

    def test_index_no_rotula_todas_las_ubicaciones_como_ficticias(self):
        status, html = self._get_text("/")
        self.assertEqual(status, 200)
        # Ya no hay una afirmación global de que todo es ficticio.
        self.assertNotIn("Las ubicaciones mostradas son ficticias", html)
        self.assertNotIn("ni muestra direcciones reales", html)
        # Leyenda y nota de demostración son dinámicas (ocultas por defecto).
        self.assertIn('id="map-demo-legend" hidden', html)
        self.assertIn('id="map-demo-note" hidden', html)

    def test_landing_incluye_widget_de_chat(self):
        status, html = self._get_text("/")
        self.assertEqual(status, 200)
        for token in (
            'id="chat-toggle"',
            'aria-expanded="false"',
            'aria-controls="chat-panel"',
            'id="chat-panel"',
            'id="chat-messages"',
            'id="chat-form"',
            'id="chat-input"',
            "Mesi",
        ):
            self.assertIn(token, html)

    def test_landing_tiene_alternativa_sin_js(self):
        status, html = self._get_text("/")
        self.assertEqual(status, 200)
        self.assertIn("<noscript>", html)

    def test_login_se_sirve(self):
        status, html = self._get_text("/login")
        self.assertEqual(status, 200)
        self.assertIn("Acceso del personal", html)
        self.assertIn('id="login-form"', html)

    def test_admin_sin_sesion_redirige_a_login(self):
        res = self.client.get("/admin")
        try:
            self.assertEqual(res.status_code, 302)
            self.assertIn("/login", res.headers.get("Location", ""))
        finally:
            res.close()

    def test_api_admin_sin_sesion_devuelve_401(self):
        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 401)
        self.assertIn("error", res.get_json())

    def test_api_locations_es_publica(self):
        res = self.client.get("/api/locations")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    # ---- Sin exposición de secretos --------------------------------------

    def _assert_no_secrets(self, text, origin):
        lowered = text.lower()
        for token in (
            "openrouter",
            "openrouter_api_key",
            "openrouter_model",
            "api_key",
            "authorization",
            "flask_secret_key",
        ):
            self.assertNotIn(token, lowered, "%s no debe exponer '%s'" % (origin, token))

    def test_js_no_expone_credenciales_ni_proveedor(self):
        for name in ("chat.js", "landing.js", "admin.js", "auth.js"):
            status, js = self._get_text("/static/js/" + name)
            self.assertEqual(status, 200)
            self._assert_no_secrets(js, name)
            self.assertNotIn("https://", js)

    def test_html_no_expone_variables_de_entorno(self):
        for path in ("/", "/login"):
            status, html = self._get_text(path)
            self.assertEqual(status, 200)
            self._assert_no_secrets(html, path)

    # ---- CSS --------------------------------------------------------------

    def test_css_define_estilos_del_chat_y_paginas(self):
        status, css = self._get_text("/static/css/style.css")
        self.assertEqual(status, 200)
        self.assertIn(".chat-toggle", css)
        self.assertIn(".chat-panel", css)
        self.assertIn(".chat-panel[hidden]", css)

        status, landing = self._get_text("/static/css/landing.css")
        self.assertEqual(status, 200)
        self.assertIn(".map-stage", landing)

        status, admin = self._get_text("/static/css/admin.css")
        self.assertEqual(status, 200)
        self.assertIn(".admin-layout", admin)


@unittest.skipUnless(NODE, "node no está disponible")
class JsRedirectTestCase(unittest.TestCase):
    """Prueba la función pura que resuelve el `next` del login (auth.js)."""

    ORIGIN = "https://app.example"

    def _safe(self, candidate):
        return run_node_module(
            "auth.js",
            "mod.safeNextPath(%s, %s)"
            % (json.dumps(candidate), json.dumps(self.ORIGIN)),
        )

    def test_ruta_interna_se_conserva(self):
        self.assertEqual(self._safe("/admin"), "/admin")
        self.assertEqual(self._safe("/admin/tasks?x=1#f"), "/admin/tasks?x=1#f")

    def test_protocol_relative_es_rechazada(self):
        self.assertEqual(self._safe("//evil.example"), "/admin")

    def test_barra_invertida_es_rechazada(self):
        # Un solo backslash y doble backslash (algunos navegadores los
        # normalizan a "/").
        self.assertEqual(self._safe("\\evil.example"), "/admin")
        self.assertEqual(self._safe("\\\\evil.example"), "/admin")
        self.assertEqual(self._safe("/\\evil.example"), "/admin")

    def test_origen_externo_es_rechazado(self):
        self.assertEqual(self._safe("https://evil.example/admin"), "/admin")

    def test_candidato_no_local_cae_al_fallback(self):
        self.assertEqual(self._safe("javascript:alert(1)"), "/admin")
        self.assertEqual(self._safe(""), "/admin")
        self.assertEqual(self._safe(None), "/admin")


@unittest.skipUnless(NODE, "node no está disponible")
class JsLandingTestCase(unittest.TestCase):
    """Prueba los helpers que deciden los avisos de datos ficticios (landing.js)."""

    def _eval(self, locations):
        expr = (
            "({show: mod.hasDemo(%s), demo: mod.demoBadgeLabel(%s[0]), "
            "real: mod.demoBadgeLabel(%s[1])})"
            % (
                json.dumps(locations),
                json.dumps(locations),
                json.dumps(locations),
            )
        )
        return run_node_module("landing.js", expr)

    def test_mezcla_demo_y_no_demo_marca_solo_la_demo(self):
        mixed = [
            {"id": 1, "is_demo": True},
            {"id": 2, "is_demo": False},
        ]
        result = self._eval(mixed)
        self.assertTrue(result["show"])
        self.assertEqual(result["demo"], "Datos ficticios de demostración")
        self.assertIsNone(result["real"])

    def test_solo_no_demo_no_muestra_aviso(self):
        real = [
            {"id": 3, "is_demo": False},
            {"id": 4, "is_demo": False},
        ]
        result = self._eval(real)
        self.assertFalse(result["show"])
        self.assertIsNone(result["demo"])
        self.assertIsNone(result["real"])

    def test_lista_vacia_no_muestra_aviso(self):
        self.assertFalse(run_node_module("landing.js", "mod.hasDemo([])"))


if __name__ == "__main__":
    unittest.main()
