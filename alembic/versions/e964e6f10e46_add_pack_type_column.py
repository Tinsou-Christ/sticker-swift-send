"""add pack type column

Revision ID: e964e6f10e46
Revises: ce1b18b366ae
Create Date: 2022-09-13 16:43:24.291431

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e964e6f10e46'
down_revision = 'ce1b18b366ae'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('packs', sa.Column('type', sa.Integer))


def downgrade():
    pass
