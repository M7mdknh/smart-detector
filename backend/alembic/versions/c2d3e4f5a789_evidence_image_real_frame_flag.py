"""incident_evidence_images.is_real_camera_frame flag

Revision ID: c2d3e4f5a789
Revises: a1c2e4f5b678
Create Date: 2026-08-29 19:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a789'
down_revision = 'a1c2e4f5b678'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('incident_evidence_images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_real_camera_frame', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('incident_evidence_images', schema=None) as batch_op:
        batch_op.drop_column('is_real_camera_frame')
