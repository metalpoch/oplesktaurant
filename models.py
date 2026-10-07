"""Modelos de datos de Oplesktaurant.

Incluye el seguimiento operativo (tareas e inventario), las cuentas de
personal (``User``) y las ubicaciones de la cadena (``RestaurantLocation``).

Las ubicaciones de demostración son **datos ficticios** y solo se cargan con el
comando explícito ``flask seed-demo-locations``; nunca de forma automática.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

TASK_STATUSES = ("pending", "completed")


def _utcnow():
    return datetime.now(timezone.utc)


class Task(db.Model):
    __tablename__ = "tasks"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'completed')", name="ck_tasks_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (
        db.CheckConstraint("quantity >= 0", name="ck_products_quantity_non_negative"),
        db.CheckConstraint(
            "quantity <= 999999999.999", name="ck_products_quantity_max"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(120), nullable=True)
    unit = db.Column(db.String(50), nullable=False)
    # Cantidad en existencia: siempre refleja el valor persistido.
    quantity = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "quantity": float(self.quantity) if self.quantity is not None else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class User(db.Model):
    """Cuenta de personal del panel. Sin auto-registro público.

    La contraseña se guarda únicamente como hash Werkzeug (``password_hash``);
    nunca en claro. Las cuentas se crean con el comando ``create-admin``.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def to_dict(self):
        return {"id": self.id, "email": self.email}


class RestaurantLocation(db.Model):
    """Ubicación de la cadena para el mapa estilizado de la landing.

    ``pos_x``/``pos_y`` son coordenadas **normalizadas** (0.0–1.0) para colocar
    los pines en el mapa isométrico; **no** son coordenadas geográficas.
    ``is_demo`` marca las ubicaciones ficticias cargadas con
    ``seed-demo-locations``.
    """

    __tablename__ = "restaurant_locations"
    __table_args__ = (
        db.CheckConstraint(
            "pos_x >= 0 AND pos_x <= 1", name="ck_locations_pos_x_normalized"
        ),
        db.CheckConstraint(
            "pos_y >= 0 AND pos_y <= 1", name="ck_locations_pos_y_normalized"
        ),
        db.UniqueConstraint("address", name="uq_locations_address"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    pos_x = db.Column(db.Float, nullable=False)
    pos_y = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "is_demo": bool(self.is_demo),
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
