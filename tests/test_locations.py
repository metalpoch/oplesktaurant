"""Pruebas de ubicaciones (mapa) y del comando de demostración."""

import unittest

from app import create_app
from models import RestaurantLocation, db
from support import CsrfClient, create_user, login


class LocationsTestCase(unittest.TestCase):
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

    def _create(self, **overrides):
        body = {
            "name": "Sucursal X",
            "address": "Calle Falsa 123, Pueblo Imaginario",
            "pos_x": 0.4,
            "pos_y": 0.6,
            "is_demo": True,
        }
        body.update(overrides)
        return self.client.post("/api/locations", json=body)

    def test_lista_publica_vacia(self):
        anon = self.app.test_client()
        res = anon.get("/api/locations")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    def test_lista_publica_mezcla_demo_y_no_demo(self):
        self._create(name="Real", address="Avenida Real 1", is_demo=False)
        self._create(name="Demo", address="Calle Falsa 2", is_demo=True)
        anon = self.app.test_client()
        data = anon.get("/api/locations").get_json()
        flags = {loc["name"]: loc["is_demo"] for loc in data}
        self.assertEqual(flags, {"Real": False, "Demo": True})

    def test_crud_ubicacion(self):
        res = self._create()
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertTrue(body["is_demo"])
        self.assertEqual(body["pos_x"], 0.4)

        # La lista pública ya muestra la ubicación.
        anon = self.app.test_client()
        self.assertEqual(len(anon.get("/api/locations").get_json()), 1)

        loc_id = body["id"]
        res = self.client.patch(
            "/api/locations/%d" % loc_id, json={"name": "Sucursal Y"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["name"], "Sucursal Y")

        self.assertEqual(
            self.client.delete("/api/locations/%d" % loc_id).status_code, 204
        )
        self.assertEqual(len(self.client.get("/api/locations").get_json()), 0)

    def test_posicion_fuera_de_rango_falla(self):
        res = self._create(pos_x=1.5)
        self.assertEqual(res.status_code, 400)
        self.assertIn("posición normalizada", res.get_json()["error"])

    def test_posicion_no_numerica_falla(self):
        res = self._create(pos_y="arriba")
        self.assertEqual(res.status_code, 400)

    def test_crear_sin_sesion_falla(self):
        anon = self.app.test_client()
        with anon.session_transaction() as sess:
            sess["csrf_token"] = "x"
        res = anon.post(
            "/api/locations",
            json={"name": "N", "address": "A", "pos_x": 0.1, "pos_y": 0.1},
            headers={"X-CSRF-Token": "x"},
        )
        self.assertEqual(res.status_code, 401)

    def test_seed_demo_es_idempotente_y_marca_demo(self):
        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["seed-demo-locations"])
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(RestaurantLocation.query.count(), 3)
        self.assertTrue(all(loc.is_demo for loc in RestaurantLocation.query.all()))

        second = runner.invoke(args=["seed-demo-locations"])
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertEqual(RestaurantLocation.query.count(), 3)

    def test_dashboard_cuenta_ubicaciones(self):
        self._create(address="Calle Falsa 1, Pueblo Imaginario")
        body = self.client.get("/api/dashboard").get_json()
        self.assertEqual(body["locations"], 1)


if __name__ == "__main__":
    unittest.main()
