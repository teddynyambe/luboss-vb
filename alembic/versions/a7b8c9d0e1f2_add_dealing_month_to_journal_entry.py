"""add dealing_month to journal_entry

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = '36191537993d'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add as nullable so we can backfill.
    op.add_column(
        "journal_entry",
        sa.Column("dealing_month", sa.Date(), nullable=True),
    )

    # 2. Backfill historical rows.
    # For rows tied to a cycle whose DECLARATION phase has a monthly_start_day,
    # use that day; otherwise use day 1 of the entry_date month.
    op.execute(
        """
        UPDATE journal_entry je
        LEFT JOIN cycle_phase cp
          ON cp.cycle_id = je.cycle_id
         AND cp.phase_type = 'declaration'
        SET je.dealing_month = DATE_FORMAT(
            je.entry_date,
            CONCAT('%Y-%m-', LPAD(COALESCE(cp.monthly_start_day, 1), 2, '0'))
        )
        WHERE je.dealing_month IS NULL
        """
    )

    # 3. Lock it down + index.
    op.alter_column("journal_entry", "dealing_month", existing_type=sa.Date(), nullable=False)
    op.create_index("ix_journal_entry_dealing_month", "journal_entry", ["dealing_month"])


def downgrade():
    op.drop_index("ix_journal_entry_dealing_month", table_name="journal_entry")
    op.drop_column("journal_entry", "dealing_month")
