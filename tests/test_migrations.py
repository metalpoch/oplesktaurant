"""Pruebas aisladas de las migraciones versionadas (Flask-Migrate/Alembic).

Aplican ``upgrade head`` y ``downgrade base`` contra una base SQLite temporal
en el directorio de trabajo del test. **Nunca** tocan la base PostgreSQL
configurada en ``.env`` ni requieren un servidor de base de datos.

Ejecutar con:

    python3 -m unittest discover -s tests -v
"""

import os
import shutil
import tempfile
import unittest

from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect

from app import create_app
from models import db

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)


class MigrationsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="oplestaurants-migrations-")
        db_path = os.path.join(self.tmpdir, "test.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + db_path,
            }
        )
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.ctx.pop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _table_names(self):
        return set(inspect(db.engine).get_table_names())

    def _check_names(self, table):
        inspector = inspect(db.engine)
        return {c["name"] for c in inspector.get_check_constraints(table)}

    def test_upgrade_crea_esquema_real_y_downgrade_lo_revierte(self):
        upgrade(directory=MIGRATIONS_DIR)

        tables = self._table_names()
        self.assertIn("tasks", tables)
        self.assertIn("products", tables)
        self.assertIn("users", tables)
        self.assertIn("restaurant_locations", tables)
        self.assertIn("alembic_version", tables)

        # Columnas reales de tasks.
        tasks_cols = {c["name"]: c for c in inspect(db.engine).get_columns("tasks")}
        self.assertEqual(
            set(tasks_cols),
            {"id", "title", "description", "status", "created_at", "updated_at"},
        )
        self.assertTrue(tasks_cols["id"]["primary_key"])
        self.assertFalse(tasks_cols["title"]["nullable"])
        self.assertTrue(tasks_cols["description"]["nullable"])
        self.assertFalse(tasks_cols["status"]["nullable"])

        # Columnas reales de products.
        products_cols = {
            c["name"]: c for c in inspect(db.engine).get_columns("products")
        }
        self.assertEqual(
            set(products_cols),
            {"id", "name", "category", "unit", "quantity", "created_at", "updated_at"},
        )
        self.assertFalse(products_cols["name"]["nullable"])
        self.assertTrue(products_cols["category"]["nullable"])
        self.assertFalse(products_cols["unit"]["nullable"])
        self.assertFalse(products_cols["quantity"]["nullable"])

        # Check constraints reales.
        self.assertIn("ck_tasks_status", self._check_names("tasks"))
        product_checks = self._check_names("products")
        self.assertIn("ck_products_quantity_non_negative", product_checks)
        self.assertIn("ck_products_quantity_max", product_checks)

        # Columnas reales de users.
        users_cols = {c["name"]: c for c in inspect(db.engine).get_columns("users")}
        self.assertEqual(
            set(users_cols),
            {"id", "email", "password_hash", "created_at", "updated_at"},
        )
        self.assertFalse(users_cols["email"]["nullable"])
        self.assertFalse(users_cols["password_hash"]["nullable"])

        # Columnas reales de restaurant_locations.
        locations_cols = {
            c["name"]: c for c in inspect(db.engine).get_columns("restaurant_locations")
        }
        self.assertEqual(
            set(locations_cols),
            {
                "id",
                "name",
                "address",
                "is_demo",
                "pos_x",
                "pos_y",
                "created_at",
                "updated_at",
            },
        )
        self.assertFalse(locations_cols["is_demo"]["nullable"])
        self.assertFalse(locations_cols["pos_x"]["nullable"])
        self.assertFalse(locations_cols["pos_y"]["nullable"])

        location_checks = self._check_names("restaurant_locations")
        self.assertIn("ck_locations_pos_x_normalized", location_checks)
        self.assertIn("ck_locations_pos_y_normalized", location_checks)

        # downgrade base elimina las tablas de negocio.
        downgrade(directory=MIGRATIONS_DIR, revision="base")
        remaining = self._table_names()
        self.assertNotIn("tasks", remaining)
        self.assertNotIn("products", remaining)
        self.assertNotIn("users", remaining)
        self.assertNotIn("restaurant_locations", remaining)

    def test_downgrade_y_upgrade_son_reversibles(self):
        upgrade(directory=MIGRATIONS_DIR)
        downgrade(directory=MIGRATIONS_DIR, revision="base")
        upgrade(directory=MIGRATIONS_DIR)
        self.assertTrue({"tasks", "products"}.issubset(self._table_names()))


if __name__ == "__main__":
    unittest.main()
