"""add_fund_requirements_to_cycle

Revision ID: add_fund_requirements_to_cycle
Revises: 3b0ed1f80dcd
Create Date: 2026-01-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_fund_requirements_to_cycle'
down_revision: Union[str, None] = '3b0ed1f80dcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add social_fund_required and admin_fund_required columns to cycle table
    op.add_column('cycle', sa.Column('social_fund_required', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('cycle', sa.Column('admin_fund_required', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    # Remove the columns
    op.drop_column('cycle', 'admin_fund_required')
    op.drop_column('cycle', 'social_fund_required')
