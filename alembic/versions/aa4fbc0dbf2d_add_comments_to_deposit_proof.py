"""add_comments_to_deposit_proof

Revision ID: aa4fbc0dbf2d
Revises: 1bf4a4ff0d38
Create Date: 2026-01-22 23:30:22.741492

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa4fbc0dbf2d'
down_revision: Union[str, None] = '1bf4a4ff0d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add comment and rejection fields to deposit_proof table
    op.add_column('deposit_proof', sa.Column('treasurer_comment', sa.Text(), nullable=True))
    op.add_column('deposit_proof', sa.Column('member_response', sa.Text(), nullable=True))
    op.add_column('deposit_proof', sa.Column('rejected_at', sa.DateTime(), nullable=True))
    op.add_column('deposit_proof', sa.Column('rejected_by', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_deposit_proof_rejected_by', 'deposit_proof', 'user', ['rejected_by'], ['id'])


def downgrade() -> None:
    # Remove comment and rejection fields
    op.drop_constraint('fk_deposit_proof_rejected_by', 'deposit_proof', type_='foreignkey')
    op.drop_column('deposit_proof', 'rejected_by')
    op.drop_column('deposit_proof', 'rejected_at')
    op.drop_column('deposit_proof', 'member_response')
    op.drop_column('deposit_proof', 'treasurer_comment')
