"""add users and restaurant_locations

Revision ID: b7f2a9c4d1e0
Revises: c3c19d47ad6c
Create Date: 2026-10-06 22:10:00.000000

Añade las tablas ``users`` (cuentas de personal) y ``restaurant_locations``
(ubicaciones del mapa estilizado, con posición normalizada x/y).

Las ubicaciones ficticias de demostración **no** se insertan aquí: se cargan
de forma opt-in con el comando ``flask seed-demo-locations``.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f2a9c4d1e0'
down_revision = 'c3c19d47ad6c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'restaurant_locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('address', sa.String(length=300), nullable=False),
        sa.Column('is_demo', sa.Boolean(), nullable=False),
        sa.Column('pos_x', sa.Float(), nullable=False),
        sa.Column('pos_y', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            'pos_x >= 0 AND pos_x <= 1', name='ck_locations_pos_x_normalized'
        ),
        sa.CheckConstraint(
            'pos_y >= 0 AND pos_y <= 1', name='ck_locations_pos_y_normalized'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('address', name='uq_locations_address'),
    )
    op.create_index(
        'ix_restaurant_locations_is_demo',
        'restaurant_locations',
        ['is_demo'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_restaurant_locations_is_demo', table_name='restaurant_locations'
    )
    op.drop_table('restaurant_locations')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
