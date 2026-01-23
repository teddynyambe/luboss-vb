"""add_status_to_deposit_proof

Revision ID: 1bf4a4ff0d38
Revises: add_monthly_start_day
Create Date: 2026-01-22 23:01:10.749518

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bf4a4ff0d38'
down_revision: Union[str, None] = 'add_monthly_start_day'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for deposit proof status
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE depositproofstatus AS ENUM ('submitted', 'approved', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Add status column with default value
    op.add_column('deposit_proof', 
        sa.Column('status', sa.Enum('submitted', 'approved', 'rejected', name='depositproofstatus', create_type=False), 
                  server_default="'submitted'", nullable=False)
    )


def downgrade() -> None:
    # Remove status column
    op.drop_column('deposit_proof', 'status')
    
    # Drop enum type
    op.execute("DROP TYPE depositproofstatus;")
