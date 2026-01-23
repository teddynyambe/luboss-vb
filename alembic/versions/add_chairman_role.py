"""add_chairman_role_to_userroleenum

Revision ID: add_chairman_role
Revises: 5563da717ca2
Create Date: 2026-01-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_chairman_role'
down_revision: Union[str, None] = '5563da717ca2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'CHAIRMAN' to the userroleenum enum
    # Note: IF NOT EXISTS is available in PostgreSQL 9.3+
    # For older versions, this will fail if the value already exists
    try:
        op.execute("ALTER TYPE userroleenum ADD VALUE IF NOT EXISTS 'CHAIRMAN'")
    except Exception:
        # If IF NOT EXISTS is not supported, try without it
        # This will fail if the value already exists, which is acceptable
        op.execute("ALTER TYPE userroleenum ADD VALUE 'CHAIRMAN'")


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values directly
    # This would require recreating the enum and updating all references
    # For safety, we'll leave a comment here
    # If downgrade is needed, it would require:
    # 1. Create new enum without CHAIRMAN
    # 2. Update all user.role columns
    # 3. Drop old enum and rename new one
    pass
