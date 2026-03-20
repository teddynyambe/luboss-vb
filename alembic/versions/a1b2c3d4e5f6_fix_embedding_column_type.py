"""change document_embedding.embedding from VECTOR to LONGTEXT

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-03-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change embedding column from VECTOR(1536) to LONGTEXT
    # This stores embeddings as JSON strings, compatible with all MySQL versions
    op.alter_column(
        'document_embedding',
        'embedding',
        existing_type=sa.Text(),
        type_=sa.Text(length=4294967295),  # LONGTEXT
        existing_nullable=False,
    )


def downgrade() -> None:
    # Note: downgrading back to VECTOR requires MySQL 9.0+ with HeatWave
    pass
