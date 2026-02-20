"""add_password_reset_to_user

Revision ID: e3f4a5b6c7d8
Revises: d1a2b3c4e5f6
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d1a2b3c4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("password_reset_token", sa.String(255), nullable=True))
    op.add_column("user", sa.Column("password_reset_expires", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "password_reset_expires")
    op.drop_column("user", "password_reset_token")
