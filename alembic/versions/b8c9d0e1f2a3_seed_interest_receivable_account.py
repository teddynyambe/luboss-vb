"""seed INTEREST_RECEIVABLE org-level ledger account

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-07 00:00:00.000000

Background
==========
We are moving to accrual-at-origination for interest revenue: the full expected
interest on a new loan is recognised as income in the loan's disbursement
month, with a matching receivable that gets drawn down as the member pays
their interest portion in subsequent declarations.

That requires an org-level ASSET account to hold the outstanding receivable.
This migration creates it if it doesn't already exist. The seed mirrors what
``scripts/setup_ledger_accounts.py`` writes, so dev environments that re-run
the seed script get the same row.
"""
from alembic import op
import sqlalchemy as sa
import uuid


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT id FROM ledger_account WHERE account_code = 'INTEREST_RECEIVABLE'")
    ).fetchone()
    if existing:
        return

    new_id = uuid.uuid4().hex
    bind.execute(
        sa.text(
            """
            INSERT INTO ledger_account
                (id, account_code, account_name, account_type, description, is_active)
            VALUES
                (:id, 'INTEREST_RECEIVABLE', 'Interest Receivable', 'asset',
                 'Interest accrued at loan origination but not yet collected from members',
                 1)
            """
        ),
        {"id": new_id},
    )


def downgrade():
    # Refuse to drop if any journal line references this account — that would
    # orphan ledger postings. Operator must clean those up manually first.
    bind = op.get_bind()
    in_use = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM journal_line jl
            JOIN ledger_account la ON la.id = jl.ledger_account_id
            WHERE la.account_code = 'INTEREST_RECEIVABLE'
            """
        )
    ).scalar()
    if in_use and in_use > 0:
        raise Exception(
            f"INTEREST_RECEIVABLE is referenced by {in_use} journal lines; "
            "cannot drop. Reverse those postings first."
        )
    bind.execute(
        sa.text("DELETE FROM ledger_account WHERE account_code = 'INTEREST_RECEIVABLE'")
    )
