#!/usr/bin/env python3
"""Verify loan-balance consistency across the three sources of truth.

For every member with an active loan, print:
  - loan_amount
  - SUM(Repayment.principal_amount)       — new source used by get_member_loan_balance
  - SUM(Declaration.declared_loan_repayment) — old source (declarations >= disbursement_date)
  - LOANS_RECEIVABLE ledger balance        — the statement's source

Any row where these three diverge points to either a reconciliation-created
duplicate loan or a stale Repayment attachment. Run before AND after the SQL
repair to confirm convergence.
"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import SessionLocal
from app.models.transaction import (
    Loan, LoanStatus, Repayment, Declaration, DeclarationStatus,
)
from app.models.member import MemberProfile
from app.models.user import User
from app.models.ledger import LedgerAccount, JournalEntry, JournalLine
from sqlalchemy import func


def main():
    db = SessionLocal()
    try:
        loans_receivable = db.query(LedgerAccount).filter(
            LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
        ).first()
        lr_id = loans_receivable.id if loans_receivable else None

        active_loans = (
            db.query(Loan)
            .filter(Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED]))
            .order_by(Loan.member_id, Loan.created_at)
            .all()
        )

        print(f"Active loans found: {len(active_loans)}\n")

        header = (
            f"{'Member':<28} {'Loan ID (8)':<10} {'Disb':<12} {'App':<4} "
            f"{'loan_amt':>10} {'rep_princ':>10} {'decl_sum':>10} {'outstd':>10}"
        )
        print(header)
        print("-" * len(header))

        per_member = {}

        for loan in active_loans:
            member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
            user = db.query(User).filter(User.id == member.user_id).first() if member else None
            name = f"{user.first_name} {user.last_name}".strip() if user else str(loan.member_id)[:8]

            rep_principal = Decimal(str(
                db.query(func.coalesce(func.sum(Repayment.principal_amount), 0))
                .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
                .filter(
                    Repayment.loan_id == loan.id,
                    JournalEntry.reversed_by.is_(None),
                    JournalEntry.reversed_at.is_(None),
                ).scalar() or 0
            ))

            decl_q = db.query(func.coalesce(func.sum(Declaration.declared_loan_repayment), 0)).filter(
                Declaration.member_id == loan.member_id,
                Declaration.status == DeclarationStatus.APPROVED,
            )
            if loan.disbursement_date:
                decl_q = decl_q.filter(Declaration.effective_month >= loan.disbursement_date)
            decl_sum = Decimal(str(decl_q.scalar() or 0))

            outstanding = loan.loan_amount - rep_principal

            has_app = "Y" if loan.application_id else "—"
            disb = loan.disbursement_date.isoformat() if loan.disbursement_date else "—"

            print(
                f"{name[:28]:<28} {str(loan.id)[:8]:<10} {disb:<12} {has_app:<4} "
                f"{float(loan.loan_amount):>10.2f} {float(rep_principal):>10.2f} "
                f"{float(decl_sum):>10.2f} {float(outstanding):>10.2f}"
            )

            per_member.setdefault(loan.member_id, []).append(
                (name, loan, rep_principal, decl_sum, outstanding)
            )

        print()
        print("=" * 80)
        print("Members with MULTIPLE active loans (likely reconciliation duplicates):")
        print("=" * 80)
        flagged = 0
        for member_id, rows in per_member.items():
            if len(rows) > 1:
                flagged += 1
                name = rows[0][0]
                total_outstd = sum(r[4] for r in rows)
                total_amt = sum(r[1].loan_amount for r in rows)
                total_rep = sum(r[2] for r in rows)
                print(
                    f"  {name:<28} loans={len(rows)}  "
                    f"sum(loan_amt)={float(total_amt):>10.2f}  "
                    f"sum(rep_princ)={float(total_rep):>10.2f}  "
                    f"sum(outstd)={float(total_outstd):>10.2f}"
                )
        if not flagged:
            print("  (none)")

        # Ledger cross-check: net LOANS_RECEIVABLE balance per member from journal lines.
        # debits (disbursements) − credits (repayments) for entries whose source ties
        # back to this member.
        if lr_id:
            print()
            print("=" * 80)
            print("LOANS_RECEIVABLE ledger balance per member (statement source of truth)")
            print("=" * 80)
            for member_id, rows in per_member.items():
                name = rows[0][0]
                # disbursement entries: source_type='loan_disbursement', source_ref in loan ids
                loan_ids_text = [str(r[1].id) for r in rows]
                disb_q = (
                    db.query(
                        func.coalesce(func.sum(JournalLine.debit_amount), 0)
                        - func.coalesce(func.sum(JournalLine.credit_amount), 0)
                    )
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .filter(
                        JournalLine.ledger_account_id == lr_id,
                        JournalEntry.reversed_by.is_(None),
                        JournalEntry.source_type == "loan_disbursement",
                        JournalEntry.source_ref.in_(loan_ids_text),
                    )
                )
                disb_net = Decimal(str(disb_q.scalar() or 0))

                # repayment credits: source_type='deposit_approval', need to filter by member
                # via deposit_proof — easier: sum credits to LR on non-reversed entries where
                # the matching Repayment.loan_id ∈ this member's loans.
                rep_credits = Decimal(str(
                    db.query(func.coalesce(func.sum(JournalLine.credit_amount), 0))
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .join(Repayment, Repayment.journal_entry_id == JournalEntry.id)
                    .filter(
                        JournalLine.ledger_account_id == lr_id,
                        JournalEntry.reversed_by.is_(None),
                        Repayment.loan_id.in_([r[1].id for r in rows]),
                    ).scalar() or 0
                ))

                ledger_outstanding = disb_net - rep_credits
                print(
                    f"  {name:<28} ledger_disb_net={float(disb_net):>10.2f}  "
                    f"ledger_rep_credits={float(rep_credits):>10.2f}  "
                    f"ledger_outstanding={float(ledger_outstanding):>10.2f}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    main()
