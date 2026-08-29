"""restricted zone membership column and incident evidence images table

Revision ID: a1c2e4f5b678
Revises: 3b1af778ba89
Create Date: 2026-08-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import app.storage.db


revision = 'a1c2e4f5b678'
down_revision = '3b1af778ba89'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('vision_evidence', schema=None) as batch_op:
        batch_op.add_column(sa.Column('restricted_zone_membership', sa.String(length=16), nullable=False, server_default='UNKNOWN'))

    op.create_table(
        'incident_evidence_images',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('incident_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', app.storage.db.UTCDateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(length=32), nullable=False),
        sa.Column('incident_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('zone_id', sa.String(length=64), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=True),
        sa.Column('ppe_helmet_state', sa.String(length=16), nullable=True),
        sa.Column('ppe_vest_state', sa.String(length=16), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('model_version', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_frame_id', sa.Integer(), nullable=True),
        sa.Column('file_path', sa.String(length=256), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.incident_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_incident_evidence_images_incident_id'), 'incident_evidence_images', ['incident_id'], unique=False)
    op.create_index(op.f('ix_incident_evidence_images_created_at'), 'incident_evidence_images', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_incident_evidence_images_created_at'), table_name='incident_evidence_images')
    op.drop_index(op.f('ix_incident_evidence_images_incident_id'), table_name='incident_evidence_images')
    op.drop_table('incident_evidence_images')
    with op.batch_alter_table('vision_evidence', schema=None) as batch_op:
        batch_op.drop_column('restricted_zone_membership')
