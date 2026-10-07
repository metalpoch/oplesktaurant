"""Pruebas del frontend público y del panel.

Verifican estructura accesible, ausencia de credenciales y el comportamiento
de acceso (la landing es pública; el panel exige sesión).

Ejecutar con:

    python3 -m unittest discover -s tests -v
"""

import json
import os
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from app import create_app
from models import db

JS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js"
)
NODE = shutil.which("node")


class StructureParser(HTMLParser):
    """Inspección de contratos HTML sin dependencias adicionales."""

    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append("Cierre inesperado: " + tag)
        else:
            self.stack.pop()


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
        self.assertIn("Oplesktaurant", html)
        self.assertIn("urban-buildings", html)
        self.assertIn("Universo ficticio de Oplesktaurant", html)

    def test_index_declara_universo_ficticio_sin_jerga_geografica(self):
        status, html = self._get_text("/")
        self.assertEqual(status, 200)
        self.assertIn("Universo ficticio de Oplesktaurant", html)
        for text in ("satelital", "x/y", "/api/locations", "panel administrativo", "Google Maps", "data-city-preset", "data-city-next", "city-card", "map-pins"):
            self.assertNotIn(text, html)

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
            "Mr. Mesi sin S",
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
        for name in ("chat.js", "landing.js", "admin.js", "auth.js", "city.js"):
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
        self.assertIn(".pavilion-front", landing)
        self.assertIn(".terrace-table", landing)
        self.assertNotIn("monolith", landing)
        status, city = self._get_text("/static/css/city.css")
        self.assertEqual(status, 200)
        for token in (".map-stage", "perspective:", "transform-style: preserve-3d", "translateZ(var(--h))", ".scene-flat", "@supports not"):
            self.assertIn(token, city)

        status, admin = self._get_text("/static/css/admin.css")
        self.assertEqual(status, 200)
        self.assertIn(".admin-layout", admin)

    def _admin_html(self):
        # Solo sesión de test; nunca consulta la DB de producción.
        from models import User
        from werkzeug.security import generate_password_hash

        user = User(email="frontend@example.com", password_hash=generate_password_hash("test12345"))
        db.session.add(user)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess["user_id"] = user.id
        status, html = self._get_text("/admin")
        self.assertEqual(status, 200)
        return html

    def test_admin_navegacion_formularios_y_contratos(self):
        html = self._admin_html()
        parser = StructureParser()
        parser.feed(html)
        self.assertEqual(parser.errors, [])
        self.assertEqual(parser.stack, [])
        ids = [attrs["id"] for _, attrs in parser.nodes if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for token in ("resumen", "operaciones", "inventario", "sucursales", "chart-tasks", "chart-products", "m-zero", "refresh-btn", "product-filter", "task-form", "product-form", "location-form", "chat-form"):
            self.assertIn(token, ids)
        targets = {attrs.get("href") for tag, attrs in parser.nodes if tag == "a"}
        for section in ("resumen", "operaciones", "inventario", "sucursales"):
            self.assertIn("#" + section, targets)
        labels = {attrs.get("for") for tag, attrs in parser.nodes if tag == "label"}
        for tag, attrs in parser.nodes:
            if tag == "input" and attrs.get("id", "").startswith(("task-", "product-", "location-")):
                self.assertIn(attrs["id"], labels)
        self.assertGreaterEqual(sum(tag == "details" for tag, _ in parser.nodes), 3)
        self.assertIn('data-chat-context="admin"', html)
        _, js = self._get_text("/static/js/admin.js")
        for referenced_id in re.findall(r'getElementById\("([^\"]+)"\)', js):
            self.assertIn(referenced_id, ids, "El contrato JS/HTML debe conservar " + referenced_id)
        self._assert_no_secrets(html, "/admin")

    def test_landing_login_html_equilibrado_y_maqueta_honesta(self):
        for path in ("/", "/login"):
            _, html = self._get_text(path)
            parser = StructureParser()
            parser.feed(html)
            self.assertEqual(parser.errors, [], path)
            self.assertEqual(parser.stack, [], path)
        _, html = self._get_text("/")
        for token in ("Universo ficticio de Oplesktaurant", "pavilion-sign\">Oplesktaurant", 'id="ambient-toggle"', 'class="urban-background" data-ambient aria-hidden="true" inert', 'id="locations-list"'):
            self.assertIn(token, html)
        self.assertNotIn("monolith", html)
        self.assertNotIn(">PLESTAURANTS<", html)
        self.assertNotIn('aria-hidden="true">O</span>', html)
        self.assertNotIn("map-svg-title", html)
        self.assertNotIn("más cercano", html)
        self.assertNotIn("Oplestaurants", html)
        self.assertIn('data-chat-context="public"', html)

    def test_paisaje_decorativo_sin_foco_y_branding_compartido(self):
        _, html = self._get_text("/")
        parser = StructureParser()
        parser.feed(html)
        self.assertEqual(parser.errors, [])
        depth = 0
        class DecorParser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                nonlocal depth
                values = dict(attrs)
                if "data-ambient" in values or depth:
                    if tag not in {"span", "div"}:
                        raise AssertionError("Elemento interactivo dentro del decorado: " + tag)
                    if "tabindex" in values:
                        raise AssertionError("Decorado no debe participar en el foco")
                    depth += 1

            def handle_endtag(self, tag):
                nonlocal depth
                if depth:
                    depth -= 1

        DecorParser().feed(html)
        for tag, attrs in parser.nodes:
            if "data-ambient" in attrs:
                self.assertEqual(attrs.get("aria-hidden"), "true")
                self.assertIn("inert", attrs)
        for path in ("/login", "/static/js/chat.js"):
            _, text = self._get_text(path)
            self.assertIn("Oplesktaurant", text)
            self.assertNotIn("Oplestaurants", text)
        _, css = self._get_text("/static/css/city.css")
        self.assertIn(".urban-universe", css)
        self.assertIn("width: 2400px", css)
        self.assertIn("overflow: hidden", css)
        self.assertIn("pointer-events: none", css)
        _, shared = self._get_text("/static/css/style.css")
        self.assertIn("body.ambient-paused [data-ambient] *::after", shared)
        self.assertIn("body:not(.ambient-ready)", shared)

    def test_movimiento_reducido_sin_bucle_permanente(self):
        _, css = self._get_text("/static/css/style.css")
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("scroll-behavior: auto", css)
        self.assertIn("animation-play-state: paused", css)
        _, js = self._get_text("/static/js/city.js")
        self.assertIn("visibilitychange", js)
        self.assertNotIn("requestAnimationFrame", js)
        self.assertNotIn("setInterval", js)

    def test_hero_opaco_sin_js_y_pausa_inmediata_no_congela_entrada(self):
        _, html = self._get_text("/")
        parser = StructureParser()
        parser.feed(html)
        heroes = [attrs for _, attrs in parser.nodes if "hero-art" in attrs.get("class", "").split()]
        self.assertEqual(len(heroes), 1)
        self.assertIn("data-ambient", heroes[0])
        self.assertNotIn("reveal", heroes[0]["class"].split())
        # Ninguna raíz ambiental puede heredar enter, que empieza con opacity=0.
        for _, attrs in parser.nodes:
            if "data-ambient" in attrs:
                self.assertNotIn("reveal", attrs.get("class", "").split())
        _, css = self._get_text("/static/css/landing.css")
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        declarations = " ".join(body for selector, body in rules if selector.strip().split("\n")[-1] == ".hero-art")
        self.assertRegex(declarations, r"opacity:\s*1\s*;")
        self.assertRegex(declarations, r"animation:\s*none\s*;")
        _, shared = self._get_text("/static/css/style.css")
        self.assertIn(".ambient-offscreen [data-ambient] *::after", shared)


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
class JsDashboardAndCityTestCase(unittest.TestCase):
    def test_regresiones_callbacks_y_geometria_node(self):
        result = subprocess.run(
            [NODE, "--test", os.path.join(os.path.dirname(__file__), "frontend_regressions.cjs")],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_donut_vacio_no_inventa_porcentaje(self):
        self.assertEqual(run_node_module("admin.js", "mod.taskDistribution(0, 0)"), {"total": 0, "completedPercent": 0})

    def test_donut_estados_reales_y_extremos(self):
        self.assertEqual(run_node_module("admin.js", "mod.taskDistribution(3, 1)"), {"total": 4, "completedPercent": 25})
        self.assertEqual(run_node_module("admin.js", "mod.taskDistribution(0, 4)")["completedPercent"], 100)
        self.assertEqual(run_node_module("admin.js", "mod.taskDistribution(4, 0)")["completedPercent"], 0)

    def test_cobertura_exactamente_cero_sin_suma_de_unidades(self):
        products = [
            {"quantity": "0.000", "unit": "kg"},
            {"quantity": "0.001", "unit": "litro"},
            {"quantity": 20, "unit": "pieza"},
            {"quantity": 0, "unit": "pieza"},
        ]
        self.assertEqual(run_node_module("admin.js", "mod.stockSummary(%s)" % json.dumps(products)), {"total": 4, "zero": 2})
        self.assertEqual(run_node_module("admin.js", "mod.stockSummary([])"), {"total": 0, "zero": 0})

    def test_fecha_invalida_no_se_presenta_como_historial(self):
        self.assertEqual(run_node_module("admin.js", "mod.formatCreated(null)"), "Sin fecha")
        self.assertEqual(run_node_module("admin.js", "mod.formatCreated('no-es-fecha')"), "Sin fecha")

    def test_maqueta_proyecta_solo_posiciones_normalizadas(self):
        self.assertEqual(run_node_module("city.js", "mod.position({pos_x:0, pos_y:1})"), {"x": 8, "y": 92})
        self.assertEqual(run_node_module("city.js", "mod.position({pos_x:0.5, pos_y:0.5})"), {"x": 50, "y": 50})
        for loc in ({}, {"pos_x": None, "pos_y": 0}, {"pos_x": -1, "pos_y": 0}, {"pos_x": 0, "pos_y": 2}, {"pos_x": "bad", "pos_y": 0}):
            self.assertIsNone(run_node_module("city.js", "mod.position(%s)" % json.dumps(loc)))


if __name__ == "__main__":
    unittest.main()
