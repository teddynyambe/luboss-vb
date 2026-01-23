"""add_reversal_fields_to_journal_entry

Revision ID: 3b0ed1f80dcd
Revises: aa4fbc0dbf2d
Create Date: 2026-01-23 00:05:26.619017

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3b0ed1f80dcd'
down_revision: Union[str, None] = 'aa4fbc0dbf2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add reversal fields to journal_entry table
    op.add_column('journal_entry', sa.Column('reversed_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('journal_entry', sa.Column('reversed_at', sa.DateTime(), nullable=True))
    op.add_column('journal_entry', sa.Column('reversal_reason', sa.Text(), nullable=True))
    
    # Add foreign key constraint for reversed_by
    op.create_foreign_key(
        'fk_journal_entry_reversed_by',
        'journal_entry',
        'user',
        ['reversed_by'],
        ['id']
    )


def downgrade() -> None:
    # Remove foreign key constraint (if it exists)
    try:
        op.drop_constraint('fk_journal_entry_reversed_by', 'journal_entry', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    # Remove reversal fields
    op.drop_column('journal_entry', 'reversal_reason')
    op.drop_column('journal_entry', 'reversed_at')
    op.drop_column('journal_entry', 'reversed_by')
