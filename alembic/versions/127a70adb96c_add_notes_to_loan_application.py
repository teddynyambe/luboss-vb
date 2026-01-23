"""add_notes_to_loan_application

Revision ID: 127a70adb96c
Revises: add_fund_requirements_to_cycle
Create Date: 2026-01-23 02:17:51.318469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '127a70adb96c'
down_revision: Union[str, None] = 'add_fund_requirements_to_cycle'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notes column to loan_application table
    op.add_column('loan_application', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove notes column from loan_application table
    op.drop_column('loan_application', 'notes')
