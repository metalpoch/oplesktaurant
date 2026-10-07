"""Pruebas de la API de Oplestaurants.

Usa SQLite in-memory mediante configuración de test, sin tocar la base de
datos por defecto (PostgreSQL). Ejecutar con:

    python3 -m unittest discover -s tests -v
"""

import unittest

from app import create_app
from models import db
from support import CsrfClient, create_user, login


class ApiTestCase(unittest.TestCase):
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
        create_user(self.app)
        self.client = self.app.test_client()
        login(self.client)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.ctx.pop()

    # ---- Dashboard --------------------------------------------------------

    def test_dashboard_vacio(self):
        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["tasks_pending"], 0)
        self.assertEqual(body["tasks_completed"], 0)
        self.assertEqual(body["products"], 0)
        self.assertEqual(body["locations"], 0)
        self.assertEqual(body["products_by_category"], [])

    def test_index_se_sirve(self):
        res = self.client.get("/")
        try:
            self.assertEqual(res.status_code, 200)
            self.assertIn(b"Oplestaurants", res.data)
        finally:
            # Cierra el archivo estático subyacente y evita ResourceWarning.
            res.close()

    # ---- Tareas -----------------------------------------------------------

    def test_crear_listar_filtrar_tarea(self):
        res = self.client.post(
            "/api/tasks", json={"title": "Revisar inventario", "description": "Hoy"}
        )
        self.assertEqual(res.status_code, 201)
        created = res.get_json()
        self.assertEqual(created["title"], "Revisar inventario")
        self.assertEqual(created["status"], "pending")

        self.assertEqual(len(self.client.get("/api/tasks").get_json()), 1)
        self.assertEqual(len(self.client.get("/api/tasks?status=pending").get_json()), 1)
        self.assertEqual(len(self.client.get("/api/tasks?status=completed").get_json()), 0)

    def test_crear_tarea_sin_titulo_falla(self):
        res = self.client.post("/api/tasks", json={"title": "   "})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_crear_tarea_sin_json_objeto_falla(self):
        res = self.client.post("/api/tasks", data="no-json", content_type="text/plain")
        self.assertEqual(res.status_code, 400)

    def test_actualizar_estado_tarea(self):
        task_id = self.client.post("/api/tasks", json={"title": "T"}).get_json()["id"]
        res = self.client.patch("/api/tasks/%d" % task_id, json={"status": "completed"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "completed")
        self.assertEqual(self.client.get("/api/dashboard").get_json()["tasks_completed"], 1)

    def test_actualizar_titulo_y_descripcion(self):
        task_id = self.client.post("/api/tasks", json={"title": "Viejo"}).get_json()["id"]
        res = self.client.patch(
            "/api/tasks/%d" % task_id,
            json={"title": "Nuevo", "description": "detalle"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["title"], "Nuevo")
        self.assertEqual(body["description"], "detalle")

    def test_estado_invalido_falla(self):
        task_id = self.client.post("/api/tasks", json={"title": "T"}).get_json()["id"]
        res = self.client.patch("/api/tasks/%d" % task_id, json={"status": "en-progreso"})
        self.assertEqual(res.status_code, 400)

    def test_filtro_estado_invalido_falla(self):
        res = self.client.get("/api/tasks?status=archivada")
        self.assertEqual(res.status_code, 400)

    def test_actualizar_tarea_sin_campos_falla(self):
        task_id = self.client.post("/api/tasks", json={"title": "T"}).get_json()["id"]
        res = self.client.patch("/api/tasks/%d" % task_id, json={})
        self.assertEqual(res.status_code, 400)

    def test_eliminar_tarea(self):
        task_id = self.client.post("/api/tasks", json={"title": "T"}).get_json()["id"]
        res = self.client.delete("/api/tasks/%d" % task_id)
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.client.get("/api/tasks").get_json(), [])

    def test_tarea_inexistente_404(self):
        self.assertEqual(self.client.get("/api/tasks/9999").status_code, 404)
        self.assertEqual(self.client.delete("/api/tasks/9999").status_code, 404)

    # ---- Productos --------------------------------------------------------

    def test_crear_listar_producto(self):
        res = self.client.post(
            "/api/products",
            json={"name": "Harina", "category": "Secos", "unit": "kg", "quantity": 5},
        )
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertEqual(body["name"], "Harina")
        self.assertEqual(body["quantity"], 5.0)
        self.assertEqual(len(self.client.get("/api/products").get_json()), 1)

    def test_producto_cantidad_por_defecto_cero(self):
        res = self.client.post(
            "/api/products", json={"name": "Sal", "unit": "kg"}
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["quantity"], 0.0)

    def test_producto_cantidad_negativa_falla(self):
        res = self.client.post(
            "/api/products",
            json={"name": "Azucar", "unit": "kg", "quantity": -1},
        )
        self.assertEqual(res.status_code, 400)

    def test_producto_mas_de_tres_decimales_falla(self):
        res = self.client.post(
            "/api/products",
            json={"name": "Especia", "unit": "g", "quantity": "0.0001"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("3 decimales", res.get_json()["error"])

    def test_producto_ceros_finales_admitidos(self):
        res = self.client.post(
            "/api/products",
            json={"name": "Especia", "unit": "g", "quantity": "1.2300"},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["quantity"], 1.23)

    def test_producto_cantidad_maxima_admitida(self):
        res = self.client.post(
            "/api/products",
            json={"name": "Granel", "unit": "kg", "quantity": "999999999.999"},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["quantity"], 999999999.999)

    def test_producto_cantidad_mayor_al_maximo_falla(self):
        res = self.client.post(
            "/api/products",
            json={"name": "Granel", "unit": "kg", "quantity": 1000000000},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("no puede superar", res.get_json()["error"])

    def test_editar_cantidad_precision_invalida_falla(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Frijol", "unit": "kg", "quantity": 2}
        ).get_json()["id"]
        res = self.client.patch(
            "/api/products/%d" % product_id, json={"quantity": "1.2345"}
        )
        self.assertEqual(res.status_code, 400)
        # La cantidad permanece intacta (sin redondeo silencioso).
        self.assertEqual(
            self.client.get("/api/products/%d" % product_id).get_json()["quantity"],
            2.0,
        )

    def test_producto_sin_unidad_falla(self):
        res = self.client.post("/api/products", json={"name": "Azucar", "unit": ""})
        self.assertEqual(res.status_code, 400)

    def test_ajustar_cantidad_suma_y_resta(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l", "quantity": 10}
        ).get_json()["id"]

        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": -3}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["quantity"], 7.0)

        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": 2.5}
        )
        self.assertEqual(res.get_json()["quantity"], 9.5)

    def test_ajuste_bajo_cero_falla(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l", "quantity": 1}
        ).get_json()["id"]
        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": -5}
        )
        self.assertEqual(res.status_code, 400)
        # La cantidad permanece intacta tras el rechazo.
        self.assertEqual(self.client.get("/api/products/%d" % product_id).get_json()["quantity"], 1.0)

    def test_ajuste_sin_delta_falla(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l"}
        ).get_json()["id"]
        res = self.client.post("/api/products/%d/quantity" % product_id, json={})
        self.assertEqual(res.status_code, 400)

    def test_ajuste_atomico_condicion_no_negativo(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l", "quantity": 1}
        ).get_json()["id"]

        # La condición atómica `quantity + delta >= 0` rechaza el ajuste y no
        # modifica el valor persistido.
        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": "-1.001"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            self.client.get("/api/products/%d" % product_id).get_json()["quantity"],
            1.0,
        )

        # Resta exacta permitida.
        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": -1}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["quantity"], 0.0)

        # En cero, cualquier delta negativo falla.
        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": "-0.001"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            self.client.get("/api/products/%d" % product_id).get_json()["quantity"],
            0.0,
        )

    def test_ajuste_delta_precision_invalida_falla(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l", "quantity": 1}
        ).get_json()["id"]
        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": "0.0001"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("3 decimales", res.get_json()["error"])

    def test_ajuste_excede_maximo_falla(self):
        product_id = self.client.post(
            "/api/products",
            json={"name": "Granel", "unit": "kg", "quantity": "999999999.999"},
        ).get_json()["id"]
        res = self.client.post(
            "/api/products/%d/quantity" % product_id, json={"delta": "0.001"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("máxima", res.get_json()["error"])
        self.assertEqual(
            self.client.get("/api/products/%d" % product_id).get_json()["quantity"],
            999999999.999,
        )

    def test_ajuste_producto_inexistente_404(self):
        res = self.client.post("/api/products/9999/quantity", json={"delta": 1})
        self.assertEqual(res.status_code, 404)

    def test_editar_producto(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Arroz", "unit": "kg", "quantity": 2}
        ).get_json()["id"]
        res = self.client.patch(
            "/api/products/%d" % product_id,
            json={"name": "Arroz integral", "category": "Secos", "unit": "kg"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["name"], "Arroz integral")
        self.assertEqual(body["category"], "Secos")

    def test_editar_cantidad_absoluta(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Frijol", "unit": "kg", "quantity": 2}
        ).get_json()["id"]
        res = self.client.patch(
            "/api/products/%d" % product_id, json={"quantity": 8}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["quantity"], 8.0)

    def test_eliminar_producto(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Pan", "unit": "pieza"}
        ).get_json()["id"]
        self.assertEqual(self.client.delete("/api/products/%d" % product_id).status_code, 204)
        self.assertEqual(self.client.get("/api/products").get_json(), [])

    def test_producto_inexistente_404(self):
        self.assertEqual(self.client.get("/api/products/9999").status_code, 404)

    def test_dashboard_refleja_datos_reales(self):
        t1 = self.client.post("/api/tasks", json={"title": "A"}).get_json()["id"]
        self.client.post("/api/tasks", json={"title": "B"})
        self.client.patch("/api/tasks/%d" % t1, json={"status": "completed"})
        self.client.post("/api/products", json={"name": "X", "unit": "kg"})

        body = self.client.get("/api/dashboard").get_json()
        self.assertEqual(body["tasks_pending"], 1)
        self.assertEqual(body["tasks_completed"], 1)
        self.assertEqual(body["products"], 1)

    def test_metodo_no_permitido_json(self):
        res = self.client.delete("/api/tasks")
        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.get_json()["error"], "Método no permitido.")

    # ---- Precisión con JSON crudo ----------------------------------------

    def test_producto_json_crudo_tres_decimales_aceptado(self):
        res = self.client.post(
            "/api/products",
            data='{"name": "Precision", "unit": "g", "quantity": 1.234}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["quantity"], 1.234)

    def test_producto_json_crudo_cuatro_decimales_falla(self):
        res = self.client.post(
            "/api/products",
            data='{"name": "Precision", "unit": "g", "quantity": 1.2345}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("3 decimales", res.get_json()["error"])

    def test_producto_json_crudo_no_pierde_decimales(self):
        # Antes del fix, Flask parseaba los números como float y
        # 1.23400000000000001 se convertía en 1.234, aceptándose. El literal
        # completo debe conservarse y rechazarse por superar los 3 decimales.
        res = self.client.post(
            "/api/products",
            data=(
                '{"name": "Precision", "unit": "g", '
                '"quantity": 1.23400000000000001}'
            ),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("3 decimales", res.get_json()["error"])
        self.assertEqual(self.client.get("/api/products").get_json(), [])

    def test_editar_json_crudo_no_pierde_decimales(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Frijol", "unit": "kg", "quantity": 2}
        ).get_json()["id"]
        res = self.client.patch(
            "/api/products/%d" % product_id,
            data='{"quantity": 1.23400000000000001}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("3 decimales", res.get_json()["error"])
        # La cantidad permanece intacta (sin redondeo silencioso).
        self.assertEqual(
            self.client.get("/api/products/%d" % product_id).get_json()["quantity"],
            2.0,
        )

    def test_ajuste_json_crudo_limite_aceptado(self):
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l", "quantity": 0}
        ).get_json()["id"]
        res = self.client.post(
            "/api/products/%d/quantity" % product_id,
            data='{"delta": 1.234}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["quantity"], 1.234)

    def test_ajuste_json_crudo_no_pierde_decimales(self):
        # Sin parseo Decimal, 1.23400000000000001 -> 1.234 y el ajuste se
        # aceptaba. Debe rechazarse conservando el literal original.
        product_id = self.client.post(
            "/api/products", json={"name": "Leche", "unit": "l", "quantity": 0}
        ).get_json()["id"]
        res = self.client.post(
            "/api/products/%d/quantity" % product_id,
            data='{"delta": 1.23400000000000001}',
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("3 decimales", res.get_json()["error"])
        self.assertEqual(
            self.client.get("/api/products/%d" % product_id).get_json()["quantity"],
            0.0,
        )

    def test_respuestas_y_dashboard_serializan(self):
        self.client.post(
            "/api/products",
            data='{"name": "Precision", "unit": "g", "quantity": 10.5}',
            content_type="application/json",
        )
        self.client.post("/api/tasks", json={"title": "T"})

        products = self.client.get("/api/products")
        self.assertEqual(products.status_code, 200)
        self.assertEqual(products.get_json()[0]["quantity"], 10.5)

        dashboard = self.client.get("/api/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        dash = dashboard.get_json()
        self.assertEqual(dash["tasks_pending"], 1)
        self.assertEqual(dash["tasks_completed"], 0)
        self.assertEqual(dash["products"], 1)


if __name__ == "__main__":
    unittest.main()
