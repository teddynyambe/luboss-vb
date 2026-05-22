"""Loan-state inspection and consolidation services.

These power the "Loan State" panel on the reconciliation page. The repair tool
lets a treasurer:
  - see all loans + repayments + ledger postings for a member,
  - collapse duplicate Loan rows into one,
  - correct the principal/interest split on an individual Repayment.

All operations preserve the ledger as the source of truth: closing a duplicate
loan reverses its disbursement journal entry; changing a repayment split posts
a correcting journal entry rather than mutating the original. The single-active-
loan rule is enforced everywhere a new Loan would be created.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transaction import (
    Loan, LoanStatus, Repayment,
    DepositProof, DepositProofStatus, DepositApproval,
    Declaration, DeclarationStatus,
)
from app.models.ledger import JournalEntry, JournalLine, LedgerAccount, AccountType
from app.services.accounting import create_journal_entry


def _hyphenate_uuid(u: UUID) -> str:
    """Match the form journal_entry.source_ref stores (str(uuid))."""
    return str(u)


def _live_disbursement_je(db: Session, loan_id: UUID) -> JournalEntry | None:
    return (
        db.query(JournalEntry)
        .filter(
            JournalEntry.source_type == "loan_disbursement",
            JournalEntry.source_ref == _hyphenate_uuid(loan_id),
            JournalEntry.reversed_by.is_(None),
            JournalEntry.reversed_at.is_(None),
        )
        .first()
    )


def get_member_loan_state(db: Session, member_id: UUID) -> dict:
    """Snapshot of every loan, repayment, and ledger total for a member."""
    loans = (
        db.query(Loan)
        .filter(Loan.member_id == member_id)
        .order_by(Loan.created_at)
        .all()
    )

    loans_payload = []
    member_ledger_disb_net = Decimal("0.00")
    member_ledger_rep_credits = Decimal("0.00")

    loans_receivable = db.query(LedgerAccount).filter(
        LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
    ).first()
    lr_id = loans_receivable.id if loans_receivable else None

    for loan in loans:
        # Repayments tied to this loan, with the live-vs-reversed flag from their JE
        repayments = (
            db.query(Repayment, JournalEntry)
            .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
            .filter(Repayment.loan_id == loan.id)
            .order_by(Repayment.repayment_date)
            .all()
        )
        rep_items = []
        live_principal = Decimal("0.00")
        live_interest = Decimal("0.00")
        for rep, je in repayments:
            is_live = je.reversed_by is None and je.reversed_at is None
            if is_live:
                live_principal += rep.principal_amount or Decimal("0.00")
                live_interest += rep.interest_amount or Decimal("0.00")
            rep_items.append({
                "id": str(rep.id),
                "loan_id": str(rep.loan_id) if rep.loan_id else None,
                "repayment_date": rep.repayment_date.isoformat() if rep.repayment_date else None,
                "principal_amount": float(rep.principal_amount or 0),
                "interest_amount": float(rep.interest_amount or 0),
                "total_amount": float(rep.total_amount or 0),
                "journal_entry_id": str(rep.journal_entry_id) if rep.journal_entry_id else None,
                "is_live": is_live,
            })

        disb_je = _live_disbursement_je(db, loan.id)
        ledger_disbursed = Decimal("0.00")
        if disb_je and lr_id:
            ledger_disbursed = Decimal(str(
                db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0))
                .filter(
                    JournalLine.journal_entry_id == disb_je.id,
                    JournalLine.ledger_account_id == lr_id,
                ).scalar() or 0
            ))
            member_ledger_disb_net += ledger_disbursed

        member_ledger_rep_credits += live_principal

        loans_payload.append({
            "id": str(loan.id),
            "loan_amount": float(loan.loan_amount or 0),
            "percentage_interest": float(loan.percentage_interest or 0),
            "number_of_instalments": loan.number_of_instalments or None,
            "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
            "loan_status": loan.loan_status.value if loan.loan_status else None,
            "application_id": str(loan.application_id) if loan.application_id else None,
            "has_live_disbursement_je": disb_je is not None,
            "ledger_disbursed": float(ledger_disbursed),
            "live_principal_paid": float(live_principal),
            "live_interest_paid": float(live_interest),
            "outstanding": float((loan.loan_amount or Decimal("0.00")) - live_principal),
            "created_at": loan.created_at.isoformat() if loan.created_at else None,
            "repayments": rep_items,
        })

    active_count = sum(
        1 for L in loans
        if L.loan_status in (LoanStatus.OPEN, LoanStatus.DISBURSED)
    )

    return {
        "member_id": str(member_id),
        "loans": loans_payload,
        "summary": {
            "active_loan_count": active_count,
            "ledger_disbursed_net": float(member_ledger_disb_net),
            "ledger_repayments_principal": float(member_ledger_rep_credits),
            "ledger_outstanding": float(member_ledger_disb_net - member_ledger_rep_credits),
        },
    }


def consolidate_loans(
    db: Session,
    member_id: UUID,
    keep_loan_id: UUID,
    new_loan_amount: Decimal,
    new_percentage_interest: Decimal | None,
    new_number_of_instalments: str | None,
    close_loan_ids: list[UUID],
    user_id: UUID,
) -> dict:
    """Collapse duplicate loans into one and reconcile the ledger to match.

    Steps:
      1. Validate inputs (loans belong to member, keep ≠ close, no overlap).
      2. For each close_loan: re-point all Repayment rows to keep_loan, reverse
         its live disbursement journal entry (if any), set status='closed'.
      3. Set keep_loan.loan_amount = new_loan_amount (plus the optional rate /
         instalment fields if provided). If that diverges from the ledger's
         current LOANS_RECEIVABLE balance for the kept loan, post a balancing
         journal entry against BANK_CASH so the books stay aligned.
      4. Commit.
    """
    if not close_loan_ids:
        raise ValueError("close_loan_ids cannot be empty — nothing to consolidate")
    if keep_loan_id in close_loan_ids:
        raise ValueError("keep_loan_id must not also appear in close_loan_ids")

    keep_loan = db.query(Loan).filter(
        Loan.id == keep_loan_id, Loan.member_id == member_id
    ).first()
    if not keep_loan:
        raise ValueError("keep_loan not found for this member")

    close_loans = db.query(Loan).filter(
        Loan.id.in_(close_loan_ids), Loan.member_id == member_id
    ).all()
    if len(close_loans) != len(close_loan_ids):
        raise ValueError("one or more close_loan_ids do not belong to this member")

    new_amount = Decimal(str(new_loan_amount))
    if new_amount < 0:
        raise ValueError("new_loan_amount cannot be negative")

    bank_cash = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "BANK_CASH"
    ).first()
    loans_receivable = db.query(LedgerAccount).filter(
        LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
    ).first()
    if not bank_cash or not loans_receivable:
        raise ValueError("BANK_CASH or LOANS_RECEIVABLE ledger account missing")

    # 2. Process each loan being closed.
    for cl in close_loans:
        # Re-point Repayments.
        db.query(Repayment).filter(Repayment.loan_id == cl.id).update(
            {Repayment.loan_id: keep_loan.id}, synchronize_session=False
        )
        # Reverse the live disbursement JE if there is one.
        disb_je = _live_disbursement_je(db, cl.id)
        if disb_je:
            disb_je.reversed_by = user_id
            disb_je.reversed_at = datetime.now()
        cl.loan_status = LoanStatus.CLOSED
        db.flush()

    # 3. Update kept loan and balance the ledger if needed.
    keep_disb_je = _live_disbursement_je(db, keep_loan.id)
    current_ledger_disbursed = Decimal("0.00")
    if keep_disb_je:
        current_ledger_disbursed = Decimal(str(
            db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0))
            .filter(
                JournalLine.journal_entry_id == keep_disb_je.id,
                JournalLine.ledger_account_id == loans_receivable.id,
            ).scalar() or 0
        ))

    keep_loan.loan_amount = new_amount
    if new_percentage_interest is not None:
        keep_loan.percentage_interest = Decimal(str(new_percentage_interest))
    if new_number_of_instalments is not None:
        keep_loan.number_of_instalments = new_number_of_instalments
    if keep_loan.loan_status not in (LoanStatus.OPEN, LoanStatus.DISBURSED):
        # If the kept loan was closed/withdrawn, reopen it.
        keep_loan.loan_status = LoanStatus.DISBURSED
    db.flush()

    delta = new_amount - current_ledger_disbursed
    if delta != Decimal("0.00"):
        # Post an adjustment so ledger LOANS_RECEIVABLE for this loan equals new_amount.
        if delta > 0:
            lines = [
                {"account_id": loans_receivable.id, "debit_amount": delta,
                 "credit_amount": Decimal("0.00"),
                 "description": f"Loan consolidation adjustment +{delta}"},
                {"account_id": bank_cash.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": delta,
                 "description": "Balancing entry for loan consolidation"},
            ]
        else:
            amt = -delta
            lines = [
                {"account_id": bank_cash.id, "debit_amount": amt,
                 "credit_amount": Decimal("0.00"),
                 "description": "Balancing entry for loan consolidation"},
                {"account_id": loans_receivable.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": amt,
                 "description": f"Loan consolidation adjustment -{amt}"},
            ]
        create_journal_entry(
            db=db,
            description=f"Loan consolidation adjustment for loan {keep_loan.id}",
            source_type="loan_consolidation",
            source_ref=str(keep_loan.id),
            lines=lines,
            created_by=user_id,
        )

    db.commit()
    return get_member_loan_state(db, member_id)


def reject_declaration(
    db: Session,
    declaration_id: UUID,
    comment: str,
    user_id: UUID,
) -> dict:
    """Reverse every live ledger posting tied to a declaration and move it
    back to a state where the member can edit + re-upload proof.

    Use case: treasurer reconciled a month for a member who hadn't actually
    paid yet. This reverses ALL components of the deposit (savings, social,
    admin, penalties, interest, principal) by reversing the underlying journal
    entry, marks the DepositProof as rejected with the treasurer's comment,
    and resets the Declaration to pending. Because journal entries are atomic
    per deposit, reversing the one JE auto-handles all sub-components.
    """
    if not comment or not comment.strip():
        raise ValueError("a comment is required when rejecting a declaration")

    declaration = db.query(Declaration).filter(Declaration.id == declaration_id).first()
    if not declaration:
        raise ValueError("declaration not found")

    proofs = (
        db.query(DepositProof)
        .filter(DepositProof.declaration_id == declaration.id)
        .all()
    )
    if not proofs:
        raise ValueError("no deposit proof found for this declaration")

    reversed_entries = 0
    proof_ids_touched: list[str] = []
    for proof in proofs:
        approval = (
            db.query(DepositApproval)
            .filter(DepositApproval.deposit_proof_id == proof.id)
            .first()
        )
        if approval and approval.journal_entry_id:
            je = db.query(JournalEntry).filter(JournalEntry.id == approval.journal_entry_id).first()
            if je and je.reversed_by is None and je.reversed_at is None:
                je.reversed_by = user_id
                je.reversed_at = datetime.now()
                reversed_entries += 1
        if proof.status == DepositProofStatus.APPROVED.value:
            proof.status = DepositProofStatus.REJECTED.value
            proof.rejected_by = user_id
            proof.rejected_at = datetime.now()
            proof.treasurer_comment = comment.strip()
            proof_ids_touched.append(str(proof.id))

    declaration.status = DeclarationStatus.PENDING
    db.commit()
    return {
        "declaration_id": str(declaration.id),
        "reversed_journal_entries": reversed_entries,
        "rejected_deposit_proofs": proof_ids_touched,
        "declaration_status": declaration.status.value,
    }


def reverse_repayment(
    db: Session,
    repayment_id: UUID,
    user_id: UUID,
) -> dict:
    """Mark a Repayment's journal entry as reversed.

    Use this to undo a repayment that was misattributed (e.g. moved onto the
    wrong loan during consolidation, or posted against a phantom loan). The
    Repayment row is kept for history; downstream balance calcs filter it out
    because they only sum non-reversed JEs. No compensating ledger entry is
    posted — the convention in this codebase is that `reversed_by` / `reversed_at`
    on the original entry is enough.
    """
    rep = db.query(Repayment).filter(Repayment.id == repayment_id).first()
    if not rep:
        raise ValueError("repayment not found")
    je = db.query(JournalEntry).filter(JournalEntry.id == rep.journal_entry_id).first()
    if not je:
        raise ValueError("journal entry not found for repayment")
    if je.reversed_by is not None or je.reversed_at is not None:
        raise ValueError("repayment journal entry is already reversed")
    je.reversed_by = user_id
    je.reversed_at = datetime.now()

    # Reset the linked DepositProof + Declaration so the member can edit the
    # declaration and re-upload proof from the Payment Proof page.
    approval = (
        db.query(DepositApproval)
        .filter(DepositApproval.journal_entry_id == je.id)
        .first()
    )
    proof_id = None
    declaration_id = None
    if approval:
        proof = db.query(DepositProof).filter(DepositProof.id == approval.deposit_proof_id).first()
        if proof:
            proof.status = DepositProofStatus.REJECTED.value
            proof.rejected_by = user_id
            proof.rejected_at = datetime.now()
            proof.treasurer_comment = (
                (proof.treasurer_comment + "\n" if proof.treasurer_comment else "")
                + "Auto-rejected after repayment reversal from reconciliation."
            )
            proof_id = str(proof.id)
            if proof.declaration_id:
                decl = db.query(Declaration).filter(Declaration.id == proof.declaration_id).first()
                if decl:
                    decl.status = DeclarationStatus.PENDING
                    declaration_id = str(decl.id)

    db.commit()
    return {
        "id": str(rep.id),
        "loan_id": str(rep.loan_id),
        "reversed": True,
        "deposit_proof_id": proof_id,
        "declaration_id": declaration_id,
    }


def move_repayment_to_loan(
    db: Session,
    repayment_id: UUID,
    new_loan_id: UUID,
    user_id: UUID,
) -> dict:
    """Re-point a Repayment to a different loan. Used when a payment was
    attributed to the wrong loan (commonly: a payment for a now-closed loan
    that ended up on the wrong duplicate during consolidation)."""
    rep = db.query(Repayment).filter(Repayment.id == repayment_id).first()
    if not rep:
        raise ValueError("repayment not found")
    new_loan = db.query(Loan).filter(Loan.id == new_loan_id).first()
    if not new_loan:
        raise ValueError("target loan not found")
    if new_loan.member_id != (db.query(Loan).filter(Loan.id == rep.loan_id).first()).member_id:
        raise ValueError("target loan belongs to a different member")
    rep.loan_id = new_loan_id
    db.commit()
    return {
        "id": str(rep.id),
        "loan_id": str(rep.loan_id),
    }


def adjust_repayment_split(
    db: Session,
    repayment_id: UUID,
    new_principal: Decimal,
    new_interest: Decimal,
    user_id: UUID,
) -> dict:
    """Reallocate principal vs interest on an existing Repayment.

    Constraint: total (principal + interest) must remain unchanged — we're
    splitting the same posted amount differently, not changing what the member
    paid. Posts a correcting journal entry that moves the delta between
    LOANS_RECEIVABLE and INTEREST_INCOME so the ledger stays in sync.
    """
    rep = db.query(Repayment).filter(Repayment.id == repayment_id).first()
    if not rep:
        raise ValueError("repayment not found")

    je = db.query(JournalEntry).filter(JournalEntry.id == rep.journal_entry_id).first()
    if not je or je.reversed_by is not None:
        raise ValueError("cannot adjust a repayment whose journal entry is reversed or missing")

    new_principal = Decimal(str(new_principal))
    new_interest = Decimal(str(new_interest))
    if new_principal < 0 or new_interest < 0:
        raise ValueError("amounts cannot be negative")

    new_total = new_principal + new_interest
    if abs(new_total - (rep.total_amount or Decimal("0.00"))) > Decimal("0.01"):
        raise ValueError(
            f"new principal+interest ({new_total}) must equal existing total ({rep.total_amount})"
        )

    principal_delta = new_principal - (rep.principal_amount or Decimal("0.00"))
    # If we're moving X from interest into principal: credit LOANS_RECEIVABLE more, credit INTEREST_INCOME less.
    if principal_delta != Decimal("0.00"):
        loans_receivable = db.query(LedgerAccount).filter(
            LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
        ).first()
        interest_income = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == "INTEREST_INCOME"
        ).first()
        if not loans_receivable or not interest_income:
            raise ValueError("LOANS_RECEIVABLE or INTEREST_INCOME ledger account missing")

        if principal_delta > 0:
            # Move principal_delta from interest into principal.
            lines = [
                {"account_id": loans_receivable.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": principal_delta,
                 "description": "Reallocate: shift to principal"},
                {"account_id": interest_income.id, "debit_amount": principal_delta,
                 "credit_amount": Decimal("0.00"),
                 "description": "Reallocate: reduce interest income"},
            ]
        else:
            amt = -principal_delta
            lines = [
                {"account_id": loans_receivable.id, "debit_amount": amt,
                 "credit_amount": Decimal("0.00"),
                 "description": "Reallocate: reduce principal credit"},
                {"account_id": interest_income.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": amt,
                 "description": "Reallocate: add to interest income"},
            ]
        create_journal_entry(
            db=db,
            description=f"Repayment split adjustment for repayment {rep.id}",
            source_type="repayment_split_adjustment",
            source_ref=str(rep.id),
            lines=lines,
            created_by=user_id,
        )

    rep.principal_amount = new_principal
    rep.interest_amount = new_interest
    rep.total_amount = new_total
    db.commit()
    db.refresh(rep)
    return {
        "id": str(rep.id),
        "principal_amount": float(rep.principal_amount),
        "interest_amount": float(rep.interest_amount),
        "total_amount": float(rep.total_amount),
    }
