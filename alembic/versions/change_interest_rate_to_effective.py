"""change_interest_rate_to_effective

Revision ID: change_interest_rate_to_effective
Revises: add_chairman_role
Create Date: 2026-01-22 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'change_interest_rate_to_effective'
down_revision: Union[str, None] = 'add_chairman_role'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new effective_rate_percent column
    op.add_column('credit_rating_interest_range', 
                  sa.Column('effective_rate_percent', sa.Numeric(5, 2), nullable=True))
    
    # Migrate data: use average of min and max, or min if max is null, or default to 12.00
    op.execute("""
        UPDATE credit_rating_interest_range
        SET effective_rate_percent = COALESCE(
            (min_rate_percent + max_rate_percent) / 2.0,
            min_rate_percent,
            12.00
        )
    """)
    
    # Make the column NOT NULL now that we have data
    op.alter_column('credit_rating_interest_range', 'effective_rate_percent', nullable=False)
    
    # Drop old columns
    op.drop_column('credit_rating_interest_range', 'min_rate_percent')
    op.drop_column('credit_rating_interest_range', 'max_rate_percent')


def downgrade() -> None:
    # Add back the old columns
    op.add_column('credit_rating_interest_range',
                  sa.Column('min_rate_percent', sa.Numeric(5, 2), nullable=True))
    op.add_column('credit_rating_interest_range',
                  sa.Column('max_rate_percent', sa.Numeric(5, 2), nullable=True))
    
    # Migrate data back: use effective_rate_percent for both min and max
    op.execute("""
        UPDATE credit_rating_interest_range
        SET min_rate_percent = effective_rate_percent,
            max_rate_percent = effective_rate_percent
    """)
    
    # Make columns NOT NULL
    op.alter_column('credit_rating_interest_range', 'min_rate_percent', nullable=False)
    op.alter_column('credit_rating_interest_range', 'max_rate_percent', nullable=False)
    
    # Drop the new column
    op.drop_column('credit_rating_interest_range', 'effective_rate_percent')
