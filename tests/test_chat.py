"""Pruebas del chat: identidad por sesión, sufijo de Mesi y errores."""

import unittest
from unittest import mock

from app import RateLimiter, create_app
from models import db
from support import CsrfClient, create_user, login


def sentences(text):
    return [s.rstrip(".!?…\"”’»)]}").strip() for s in text.split(". ") if s]


class ChatTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "OPENROUTER_API_KEY": None,
                "OPENROUTER_MODEL": None,
            }
        )
        self.app.test_client_class = CsrfClient
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        create_user(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    def test_publico_es_mesi_y_termina_con_sufijo(self):
        with mock.patch(
            "chat._call_openrouter",
            return_value="Hola amigo. Bienvenido a Oplestaurants.",
        ):
            res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["identity"], "mesi")
        for s in sentences(body["reply"]):
            self.assertTrue(s.endswith("que mira bobo"), s)

    def test_mesi_no_confia_en_el_modelo_para_el_sufijo(self):
        with mock.patch(
            "chat._call_openrouter", return_value="Una sola oración sin sufijo"
        ):
            res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertTrue(res.get_json()["reply"].endswith("que mira bobo"))

    def test_mesi_no_duplica_el_sufijo(self):
        with mock.patch(
            "chat._call_openrouter",
            return_value="Hola que mira bobo",
        ):
            res = self.client.post("/api/chat", json={"message": "hola"})
        reply = res.get_json()["reply"]
        self.assertEqual(reply.count("que mira bobo"), 1)

    def test_autenticado_es_nbapeh_sin_sufijo(self):
        login(self.client)
        with mock.patch(
            "chat._call_openrouter",
            return_value="Usa el panel para gestionar tareas.",
        ):
            res = self.client.post("/api/chat", json={"message": "¿cómo hago?"})
        body = res.get_json()
        self.assertEqual(body["identity"], "nbapeh")
        self.assertNotIn("que mira bobo", body["reply"])

    def test_fallback_sin_configuracion_no_revela_datos(self):
        res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertEqual(res.status_code, 200)
        reply = res.get_json()["reply"]
        self.assertTrue(reply.rstrip(".!?…\"”’»)]}").endswith("que mira bobo"))
        self.assertNotIn("openrouter", reply.lower())
        self.assertNotIn("api", reply.lower())

    def test_error_del_proveedor_es_neutral(self):
        with mock.patch("chat._call_openrouter", return_value=None):
            res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("Inténtalo", res.get_json()["reply"])

    def test_mensaje_vacio_falla(self):
        res = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(res.status_code, 400)

    def test_mensaje_demasiado_largo_falla(self):
        res = self.client.post("/api/chat", json={"message": "x" * 1001})
        self.assertEqual(res.status_code, 400)

    # ---- Sufijo por oración sin espacio tras el punto ---------------------

    def test_mesi_sufijo_por_oracion_sin_espacio_tras_punto(self):
        with mock.patch("chat._call_openrouter", return_value="Hola.Mundo"):
            res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.get_json()["reply"],
            "Hola que mira bobo. Mundo que mira bobo",
        )

    def test_mesi_no_parte_decimales_al_agregar_sufijo(self):
        with mock.patch("chat._call_openrouter", return_value="3.14 es pi"):
            res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertEqual(
            res.get_json()["reply"], "3.14 es pi que mira bobo"
        )

    def test_mesi_sufijo_con_cierre_de_comilla(self):
        # El cierre de comilla tras la puntuación no debe impedir el corte.
        with mock.patch(
            "chat._call_openrouter", return_value='"Hola." Mundo.'
        ):
            res = self.client.post("/api/chat", json={"message": "hola"})
        self.assertEqual(
            res.get_json()["reply"],
            '"Hola que mira bobo." Mundo que mira bobo.',
        )

    # ---- Límite de tamaño y rate limit ------------------------------------

    def test_cuerpo_demasiado_grande_devuelve_413_json(self):
        # 1 MiB supera el MAX_CONTENT_LENGTH por defecto (64 KiB).
        res = self.client.post(
            "/api/chat",
            data='{"message": "' + ("x" * (1024 * 1024)) + '"}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 413)
        self.assertIn("error", res.get_json())

    def test_rate_limit_429_no_llama_proveedor_y_ignora_xff(self):
        # El rate limit es por IP de conexión: cambiar X-Forwarded-For en cada
        # petición no crea buckets distintos. Con el límite por defecto (10/min),
        # la petición 11 se rechaza y no invoca al proveedor.
        responses = []
        with mock.patch("chat._call_openrouter", return_value="Hola.Mundo") as provider:
            for i in range(11):
                responses.append(
                    self.client.post(
                        "/api/chat",
                        json={"message": "hola"},
                        headers={"X-Forwarded-For": "203.0.113.%d" % i},
                    )
                )
        self.assertEqual([r.status_code for r in responses[:10]], [200] * 10)
        self.assertEqual(responses[10].status_code, 429)
        self.assertIn("error", responses[10].get_json())
        self.assertEqual(provider.call_count, 10)

    def test_rate_limiter_limpia_buckets_viejos(self):
        limiter = RateLimiter(limit=1, window=10)
        self.assertTrue(limiter.allow("a", now=0))
        self.assertFalse(limiter.allow("a", now=0))
        self.assertEqual(limiter.bucket_count(), 1)
        # Al avanzar la ventana se poda el bucket inactivo y se crea el nuevo.
        self.assertTrue(limiter.allow("b", now=100))
        self.assertEqual(limiter.bucket_count(), 1)


if __name__ == "__main__":
    unittest.main()
