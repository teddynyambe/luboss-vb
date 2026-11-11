"""add_deposit_proof_file

Additional proof-of-payment files per DepositProof, so a member (or the
treasurer on their behalf) can attach a second or third deposit slip to one
declaration. `deposit_proof.upload_path` stays the first file.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'deposit_proof_file',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('deposit_proof_id', sa.Uuid(), nullable=False),
        sa.Column('upload_path', sa.String(length=500), nullable=False),
        sa.Column('uploaded_by', sa.Uuid(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['deposit_proof_id'], ['deposit_proof.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('deposit_proof_file', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deposit_proof_file_deposit_proof_id'), ['deposit_proof_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('deposit_proof_file', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_deposit_proof_file_deposit_proof_id'))
    op.drop_table('deposit_proof_file')
