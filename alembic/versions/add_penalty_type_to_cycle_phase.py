"""add_penalty_type_to_cycle_phase

Revision ID: add_penalty_type_to_cycle_phase
Revises: add_end_day_and_penalty
Create Date: 2026-01-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_penalty_type_to_cycle_phase'
down_revision: Union[str, None] = 'add_end_day_and_penalty'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add penalty_type_id column (nullable UUID foreign key to penalty_type)
    op.add_column('cycle_phase', 
        sa.Column('penalty_type_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_cycle_phase_penalty_type_id',
        'cycle_phase', 'penalty_type',
        ['penalty_type_id'], ['id']
    )
    
    # Add auto_apply_penalty column (boolean, default False)
    op.add_column('cycle_phase',
        sa.Column('auto_apply_penalty', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    # Remove the columns
    op.drop_constraint('fk_cycle_phase_penalty_type_id', 'cycle_phase', type_='foreignkey')
    op.drop_column('cycle_phase', 'auto_apply_penalty')
    op.drop_column('cycle_phase', 'penalty_type_id')
