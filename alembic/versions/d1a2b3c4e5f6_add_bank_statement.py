"""add_bank_statement

Revision ID: d1a2b3c4e5f6
Revises: c0316f1ba32a
Create Date: 2026-02-17 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1a2b3c4e5f6'
down_revision: Union[str, None] = 'c0316f1ba32a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bank_statement',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('cycle_id', sa.Uuid(), nullable=False),
        sa.Column('statement_month', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('upload_path', sa.String(length=500), nullable=False),
        sa.Column('uploaded_by', sa.Uuid(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['cycle_id'], ['cycle.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bank_statement', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bank_statement_cycle_id'), ['cycle_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('bank_statement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bank_statement_cycle_id'))
    op.drop_table('bank_statement')
