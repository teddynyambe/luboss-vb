"""One-shot retrofit: convert historical loans to accrual-at-origination.

WHAT THIS DOES
==============
Before this change, interest was recognised as income only when paid (cash
basis). The new policy is that the FULL expected interest on a loan is income
in the loan's disbursement month, and subsequent payments draw down a
receivable rather than recognising new income.

For every loan already in the system this script posts a single corrective
journal entry that re-states the books onto the accrual basis:

    Dr  INTEREST_RECEIVABLE    (expected − already_paid)
    Cr  INTEREST_INCOME        (expected − already_paid)

After this:
- INTEREST_INCOME ends up at the full expected interest for each loan
  (already-paid portion + corrective remainder = full expected).
- INTEREST_RECEIVABLE ends up at the outstanding portion (expected − paid).

Idempotent: each retrofit JE carries source_type = 'interest_accrual_retrofit'
and source_ref = loan id, and the script skips any loan whose retrofit JE
already exists. Safe to re-run.

Skips:
- Loans without a disbursement_date (never properly disbursed).
- Loans whose net correction is 0 (fully-paid or zero-interest loans).
- Loans with no INTEREST_RECEIVABLE / INTEREST_INCOME accounts in the DB
  (run scripts/setup_ledger_accounts.py + migration b8c9d0e1f2a3 first).

DEALING MONTH
=============
The retrofit JE is bucketed under the loan's disbursement month (via the
cycle's declaration-phase monthly_start_day), so the monthly Interest
Revenue report shows the corrected accrual under the right period.

RUN
===
    source app/venv/bin/activate
    python scripts/retrofit_interest_accrual.py            # dry-run
    python scripts/retrofit_interest_accrual.py --apply    # commit changes
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

# Make the `app` package importable when this script is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.models.ledger import JournalEntry, JournalLine, LedgerAccount
from app.models.transaction import Loan, Repayment
from app.services.accounting import create_journal_entry, get_dealing_month_date


SOURCE_TYPE = "interest_accrual_retrofit"


def _expected_interest(loan: Loan) -> Decimal:
    return (
        (loan.loan_amount or Decimal("0.00"))
        * (loan.percentage_interest or Decimal("0.00"))
        / Decimal("100")
    ).quantize(Decimal("0.01"))


def _interest_already_paid(db: Session, loan_id) -> Decimal:
    rows = (
        db.query(Repayment, JournalEntry)
        .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
        .filter(
            Repayment.loan_id == loan_id,
            JournalEntry.reversed_by.is_(None),
            JournalEntry.reversed_at.is_(None),
        )
        .all()
    )
    return sum(
        (r.interest_amount or Decimal("0.00") for r, _je in rows),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))


def _already_retrofitted(db: Session, loan_id) -> bool:
    return (
        db.query(JournalEntry)
        .filter(
            JournalEntry.source_type == SOURCE_TYPE,
            JournalEntry.source_ref == str(loan_id),
            JournalEntry.reversed_by.is_(None),
            JournalEntry.reversed_at.is_(None),
        )
        .first()
        is not None
    )


def retrofit(db: Session, apply: bool) -> dict:
    int_rec = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_RECEIVABLE"
    ).first()
    int_inc = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_INCOME"
    ).first()
    if not int_rec or not int_inc:
        print(
            "ERROR: INTEREST_RECEIVABLE or INTEREST_INCOME ledger account missing.\n"
            "Run scripts/setup_ledger_accounts.py and `alembic upgrade head` first."
        )
        sys.exit(2)

    loans = (
        db.query(Loan)
        .filter(Loan.disbursement_date.isnot(None))
        .order_by(Loan.disbursement_date.asc())
        .all()
    )

    summary = {
        "loans_total": len(loans),
        "loans_retrofitted": 0,
        "loans_skipped_already_done": 0,
        "loans_skipped_zero_net": 0,
        "loans_skipped_no_interest": 0,
        "total_receivable_posted": Decimal("0.00"),
        "total_income_recognised": Decimal("0.00"),
    }

    for loan in loans:
        expected = _expected_interest(loan)
        if expected <= 0:
            summary["loans_skipped_no_interest"] += 1
            continue

        if _already_retrofitted(db, loan.id):
            summary["loans_skipped_already_done"] += 1
            continue

        paid = _interest_already_paid(db, loan.id)
        net = (expected - paid).quantize(Decimal("0.01"))
        if net <= 0:
            summary["loans_skipped_zero_net"] += 1
            continue

        print(
            f"  Loan {str(loan.id)[:8]} "
            f"(member {str(loan.member_id)[:8]}, "
            f"disbursed {loan.disbursement_date}, "
            f"K{loan.loan_amount} @ {loan.percentage_interest}%): "
            f"expected K{expected}, paid K{paid}, retrofit K{net}"
        )

        if apply:
            create_journal_entry(
                db=db,
                description=(
                    f"Interest accrual retrofit — loan {str(loan.id)[:8]} "
                    f"({loan.percentage_interest}% on K{loan.loan_amount}, "
                    f"expected K{expected} − already paid K{paid})"
                )[:255],
                lines=[
                    {
                        "account_id": int_rec.id,
                        "debit_amount": net,
                        "credit_amount": Decimal("0.00"),
                        "description": "Receivable for outstanding interest",
                    },
                    {
                        "account_id": int_inc.id,
                        "debit_amount": Decimal("0.00"),
                        "credit_amount": net,
                        "description": "Interest income recognised retroactively at origination",
                    },
                ],
                dealing_month=get_dealing_month_date(db, loan.cycle_id, loan.disbursement_date),
                cycle_id=loan.cycle_id,
                source_ref=str(loan.id),
                source_type=SOURCE_TYPE,
                created_by=None,  # system-generated retrofit
            )

        summary["loans_retrofitted"] += 1
        summary["total_receivable_posted"] += net
        summary["total_income_recognised"] += net

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually post journal entries. Without this flag, runs as a dry-run.",
    )
    args = parser.parse_args()

    print("=== Interest accrual retrofit ===")
    print(f"Mode: {'APPLY (will commit)' if args.apply else 'DRY-RUN (no changes)'}")
    print()

    with SessionLocal() as db:
        summary = retrofit(db, apply=args.apply)
        if args.apply:
            db.commit()

    print()
    print("=== Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if not args.apply:
        print()
        print("Re-run with --apply to commit.")


if __name__ == "__main__":
    main()
