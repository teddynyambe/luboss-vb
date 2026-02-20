"""add loan_term_option table

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-02-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    loan_term_option = op.create_table(
        "loan_term_option",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("term_months", sa.String(10), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.bulk_insert(loan_term_option, [
        {"term_months": "1", "sort_order": 1},
        {"term_months": "2", "sort_order": 2},
        {"term_months": "3", "sort_order": 3},
        {"term_months": "4", "sort_order": 4},
    ])


def downgrade():
    op.drop_table("loan_term_option")
