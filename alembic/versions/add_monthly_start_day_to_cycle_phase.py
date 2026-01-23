"""add_monthly_start_day_to_cycle_phase

Revision ID: add_monthly_start_day
Revises: change_interest_rate_to_effective
Create Date: 2026-01-22 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_monthly_start_day'
down_revision: Union[str, None] = 'change_interest_rate_to_effective'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add monthly_start_day column to cycle_phase table
    op.add_column('cycle_phase', 
                  sa.Column('monthly_start_day', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Remove monthly_start_day column
    op.drop_column('cycle_phase', 'monthly_start_day')
