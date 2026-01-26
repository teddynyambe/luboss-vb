"""merge simplify_member_status and update_penalty_status

Revision ID: 21a482f0d8f7
Revises: simplify_member_status, update_penalty_status
Create Date: 2026-01-26 08:19:55.572762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21a482f0d8f7'
down_revision: Union[str, None] = ('simplify_member_status', 'update_penalty_status')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
