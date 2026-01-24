"""add_end_day_and_penalty_to_cycle_phase

Revision ID: add_end_day_and_penalty
Revises: 127a70adb96c
Create Date: 2026-01-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_end_day_and_penalty'
down_revision: Union[str, None] = '127a70adb96c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add monthly_end_day and penalty_amount columns to cycle_phase table
    op.add_column('cycle_phase', 
                  sa.Column('monthly_end_day', sa.Integer(), nullable=True))
    op.add_column('cycle_phase', 
                  sa.Column('penalty_amount', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    # Remove the columns
    op.drop_column('cycle_phase', 'penalty_amount')
    op.drop_column('cycle_phase', 'monthly_end_day')
