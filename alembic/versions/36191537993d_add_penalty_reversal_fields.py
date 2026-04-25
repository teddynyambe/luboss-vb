"""add_penalty_reversal_fields

Revision ID: 36191537993d
Revises: 6506e8a1d97f
Create Date: 2026-04-24 22:09:44.938220

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '36191537993d'
down_revision: Union[str, None] = '6506e8a1d97f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('penalty_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reversal_requested_by', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('reversal_requested_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reversal_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('reversed_by', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('reversed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reversal_journal_entry_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(None, 'user', ['reversed_by'], ['id'])
        batch_op.create_foreign_key(None, 'journal_entry', ['reversal_journal_entry_id'], ['id'])
        batch_op.create_foreign_key(None, 'user', ['reversal_requested_by'], ['id'])

    # ### end Alembic commands ###


def downgrade() -> None:
    with op.batch_alter_table('penalty_record', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('reversal_journal_entry_id')
        batch_op.drop_column('reversed_at')
        batch_op.drop_column('reversed_by')
        batch_op.drop_column('reversal_reason')
        batch_op.drop_column('reversal_requested_at')
        batch_op.drop_column('reversal_requested_by')
