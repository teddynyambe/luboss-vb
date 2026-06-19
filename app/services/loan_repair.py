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
from datetime import datetime, date
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transaction import (
    Loan, LoanStatus, Repayment,
    DepositProof, DepositProofStatus, DepositApproval,
    Declaration, DeclarationStatus,
)
from app.models.ledger import JournalEntry, JournalLine, LedgerAccount, AccountType
from app.services.accounting import create_journal_entry, get_dealing_month_date
from app.services.transaction_repair import _require_description


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


def loan_has_live_disbursement(db: Session, loan_id: UUID) -> bool:
    """True if this loan's disbursement journal entry exists and has NOT been
    reversed. Use this everywhere you'd otherwise be tempted to show a loan
    that's been ledger-reversed — those loans should disappear from every
    user-facing view (Loans cards, reports, balances) even though the Loan
    row stays in the DB for audit."""
    return _live_disbursement_je(db, loan_id) is not None


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

        # Accrual-at-origination: expected interest is the full charge on the loan,
        # outstanding interest is what's still owed after live payments.
        expected_interest = (
            (loan.loan_amount or Decimal("0.00"))
            * (loan.percentage_interest or Decimal("0.00"))
            / Decimal("100")
        ).quantize(Decimal("0.01"))
        interest_outstanding = max(Decimal("0.00"), expected_interest - live_interest)

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
            "expected_interest": float(expected_interest),
            "interest_outstanding": float(interest_outstanding),
            "created_at": loan.created_at.isoformat() if loan.created_at else None,
            "repayments": rep_items,
        })

    active_count = sum(
        1 for L in loans
        if L.loan_status in (LoanStatus.OPEN, LoanStatus.DISBURSED)
    )

    # Interest totals across ALL loans (active + closed). Closed loans with
    # interest still owed should remain visible in the summary so a treasurer
    # sees the outstanding receivable they need to chase or write off.
    total_interest_expected = sum(
        (Decimal(str(l["expected_interest"])) for l in loans_payload),
        Decimal("0.00"),
    )
    total_interest_paid = sum(
        (Decimal(str(l["live_interest_paid"])) for l in loans_payload),
        Decimal("0.00"),
    )
    total_interest_outstanding = sum(
        (Decimal(str(l["interest_outstanding"])) for l in loans_payload),
        Decimal("0.00"),
    )

    return {
        "member_id": str(member_id),
        "loans": loans_payload,
        "summary": {
            "active_loan_count": active_count,
            "ledger_disbursed_net": float(member_ledger_disb_net),
            "ledger_repayments_principal": float(member_ledger_rep_credits),
            "ledger_outstanding": float(member_ledger_disb_net - member_ledger_rep_credits),
            "interest_expected_total": float(total_interest_expected),
            "interest_paid_total": float(total_interest_paid),
            "interest_outstanding_total": float(total_interest_outstanding),
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
            dealing_month=get_dealing_month_date(db, keep_loan.cycle_id, date.today()),
            cycle_id=keep_loan.cycle_id,
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
            # Drop the now-stale approval row. The unique constraint on
            # deposit_proof_id would otherwise block a future re-approval of the
            # same proof. The audit trail lives on the reversed journal entry.
            db.delete(approval)
        if proof.status == DepositProofStatus.APPROVED.value:
            proof.status = DepositProofStatus.REJECTED.value
            proof.rejected_by = user_id
            proof.rejected_at = datetime.now()
            proof.treasurer_comment = comment.strip()
            proof_ids_touched.append(str(proof.id))
        # Whether the proof was APPROVED-and-just-rejected or already REJECTED,
        # delete the file from disk to avoid accumulating redundant attachments.
        # The DB row keeps upload_path for audit (column is NOT NULL anyway);
        # callers serving the file should treat a missing file as "no longer
        # available" rather than an error.
        if proof.upload_path:
            import os
            try:
                if os.path.isfile(proof.upload_path):
                    os.remove(proof.upload_path)
            except OSError:
                pass

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
            # Free the file from disk; DB row keeps upload_path for audit
            # (column is NOT NULL — callers must treat missing files as
            # "no longer available").
            if proof.upload_path:
                import os
                try:
                    if os.path.isfile(proof.upload_path):
                        os.remove(proof.upload_path)
                except OSError:
                    pass
            proof_id = str(proof.id)
            if proof.declaration_id:
                decl = db.query(Declaration).filter(Declaration.id == proof.declaration_id).first()
                if decl:
                    decl.status = DeclarationStatus.PENDING
                    declaration_id = str(decl.id)
        # Drop the stale approval row so a future re-approval of this same
        # deposit proof doesn't trip the unique constraint on deposit_proof_id.
        db.delete(approval)

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
            dealing_month=je.dealing_month,
            cycle_id=je.cycle_id,
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


# ---------------------------------------------------------------------------
# Loan-level repair actions (treasurer "Loan State" panel)
# ---------------------------------------------------------------------------

def _live_repayments_for_loan(db: Session, loan_id: UUID) -> list[Repayment]:
    """Repayments whose underlying journal entry is NOT reversed."""
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
    return [r for r, _ in rows]


def reopen_loan(db: Session, loan_id: UUID, reason: str, user_id: UUID) -> dict:
    """Set a closed loan back to OPEN. Refuses if its disbursement JE has been
    reversed — that would leave a phantom open loan with no ledger backing."""
    reason = _require_description(reason)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")
    if loan.loan_status not in (LoanStatus.CLOSED,):
        raise ValueError(f"loan is not closed (current status: {loan.loan_status.value if loan.loan_status else 'unknown'})")
    if not _live_disbursement_je(db, loan.id):
        raise ValueError(
            "cannot reopen: this loan has no live disbursement journal entry. "
            "It would be an open loan with no money owed."
        )
    loan.loan_status = LoanStatus.OPEN
    db.commit()
    return {"id": str(loan.id), "loan_status": loan.loan_status.value, "reason": reason}


def close_loan(db: Session, loan_id: UUID, reason: str, user_id: UUID) -> dict:
    """Force a loan to CLOSED status. Used to retire a loan manually; does not
    post any compensating ledger entry. Caller's reason is recorded for audit."""
    reason = _require_description(reason)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")
    if loan.loan_status == LoanStatus.CLOSED:
        raise ValueError("loan is already closed")
    loan.loan_status = LoanStatus.CLOSED
    db.commit()
    return {"id": str(loan.id), "loan_status": loan.loan_status.value, "reason": reason}


def restore_loan_disbursement(
    db: Session, loan_id: UUID, reason: str, user_id: UUID
) -> dict:
    """Un-reverse a loan's disbursement journal entry — the recovery action
    for a disbursement that was reversed in error. Clears the reversed_by /
    reversed_at on the most recent reversed disbursement JE for this loan,
    bringing the K_amount back onto LOANS_RECEIVABLE so the ledger balances
    against the repayments that may still be attached.

    Refused if a live (un-reversed) disbursement JE already exists — that
    would mean restoring would double-count the principal.
    """
    reason = _require_description(reason)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")

    # Refuse if there's already a live disbursement (avoid duplicates).
    if _live_disbursement_je(db, loan.id) is not None:
        raise ValueError(
            "this loan already has a live disbursement journal entry; "
            "nothing to restore"
        )

    # Find the most recently reversed disbursement JE for this loan.
    reversed_je = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.source_type == "loan_disbursement",
            JournalEntry.source_ref == _hyphenate_uuid(loan.id),
            JournalEntry.reversed_by.isnot(None),
        )
        .order_by(JournalEntry.reversed_at.desc())
        .first()
    )
    if reversed_je is None:
        raise ValueError(
            "no reversed disbursement journal entry found for this loan to restore"
        )

    reversed_je.reversed_by = None
    reversed_je.reversed_at = None
    # Stamp the restoration reason onto the JE so the audit trail shows why
    # the original reversal was undone. Keep the previous text if any.
    prev = (reversed_je.reversal_reason or "").strip()
    note = f"[Restored by treasurer: {reason}]"
    reversed_je.reversal_reason = f"{prev} {note}".strip() if prev else note

    db.commit()
    return {
        "id": str(loan.id),
        "restored_journal_entry_id": str(reversed_je.id),
        "loan_status": loan.loan_status.value if loan.loan_status else None,
        "reason": reason,
    }


def reverse_loan_disbursement(
    db: Session, loan_id: UUID, reason: str, user_id: UUID
) -> dict:
    """Reverse a loan's disbursement journal entry. Refuses if any live
    repayment is still attached — those would be left orphaned. Treasurer
    must reverse or move repayments off the loan first."""
    reason = _require_description(reason)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")

    live_reps = _live_repayments_for_loan(db, loan.id)
    if live_reps:
        raise ValueError(
            f"cannot reverse disbursement: {len(live_reps)} live repayment(s) still "
            f"attached to this loan. Reverse or move them first."
        )

    disb_je = _live_disbursement_je(db, loan.id)
    if not disb_je:
        raise ValueError("no live disbursement journal entry found for this loan")

    disb_je.reversed_by = user_id
    disb_je.reversed_at = datetime.now()
    disb_je.reversal_reason = reason
    loan.loan_status = LoanStatus.CLOSED
    db.commit()
    return {
        "id": str(loan.id),
        "loan_status": loan.loan_status.value,
        "reversed_journal_entry_id": str(disb_je.id),
        "reason": reason,
    }


def reverse_all_repayments_for_loan(
    db: Session, loan_id: UUID, reason: str, user_id: UUID
) -> dict:
    """Bulk: reverse every live repayment attached to a loan. Each repayment's
    deposit approval is also rolled back (matches single-row reverse_repayment
    behavior) so the linked declarations return to PENDING for re-upload."""
    reason = _require_description(reason)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")

    live_reps = _live_repayments_for_loan(db, loan.id)
    if not live_reps:
        raise ValueError("no live repayments to reverse on this loan")

    reversed_ids: list[str] = []
    for rep in live_reps:
        # Delegate to reverse_repayment so DepositProof/Declaration rollback
        # stays consistent with the per-row action.
        try:
            reverse_repayment(db, rep.id, user_id)
            reversed_ids.append(str(rep.id))
        except ValueError:
            # Already reversed by a concurrent action — skip.
            continue

    return {
        "loan_id": str(loan.id),
        "reversed_repayment_ids": reversed_ids,
        "count": len(reversed_ids),
        "reason": reason,
    }


def move_all_repayments_for_loan(
    db: Session,
    loan_id: UUID,
    new_loan_id: UUID,
    reason: str,
    user_id: UUID,
) -> dict:
    """Bulk: re-point every Repayment row currently on `loan_id` to `new_loan_id`.
    Only moves rows where the new loan belongs to the same member."""
    reason = _require_description(reason)
    if loan_id == new_loan_id:
        raise ValueError("source and target loans are the same")

    src_loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not src_loan:
        raise ValueError("source loan not found")
    dst_loan = db.query(Loan).filter(Loan.id == new_loan_id).first()
    if not dst_loan:
        raise ValueError("target loan not found")
    if src_loan.member_id != dst_loan.member_id:
        raise ValueError("target loan belongs to a different member")

    reps = db.query(Repayment).filter(Repayment.loan_id == loan_id).all()
    if not reps:
        raise ValueError("no repayments to move on this loan")

    moved_ids = [str(r.id) for r in reps]
    for r in reps:
        r.loan_id = new_loan_id
    db.commit()
    return {
        "from_loan_id": str(loan_id),
        "to_loan_id": str(new_loan_id),
        "moved_repayment_ids": moved_ids,
        "count": len(moved_ids),
        "reason": reason,
    }


def edit_loan_terms(
    db: Session,
    loan_id: UUID,
    new_term_months: str | None,
    new_percentage_interest: Decimal | None,
    reason: str,
    user_id: UUID,
    new_loan_amount: Decimal | None = None,
) -> dict:
    """Edit a loan's principal, term, and/or interest rate.

    Posts a single correcting JE that reconciles BOTH the principal and the
    accrued interest with the new terms:

      principal_delta = new_amount − old_amount
      interest_delta  = (new_amount × new_rate) − (old_amount × old_rate)

    Principal correction:
        principal_delta > 0  →  Dr LOANS_RECEIVABLE / Cr BANK_CASH
        principal_delta < 0  →  Dr BANK_CASH        / Cr LOANS_RECEIVABLE
    Interest correction:
        interest_delta  > 0  →  Dr INTEREST_RECEIVABLE / Cr INTEREST_INCOME
        interest_delta  < 0  →  Dr INTEREST_INCOME     / Cr INTEREST_RECEIVABLE

    The correcting JE's dealing_month is the loan's disbursement month so
    the Loan/Revenue report groups the correction under the right period.

    Refused if the loan's disbursement JE has been reversed — restore the
    disbursement first. Repayment dates and amounts are not touched.

    At least one of new_loan_amount, new_term_months, new_percentage_interest
    must be set. Pass the others as None to leave them unchanged.
    """
    reason = _require_description(reason)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")

    if (
        new_term_months is None
        and new_percentage_interest is None
        and new_loan_amount is None
    ):
        raise ValueError(
            "nothing to change — specify a new amount, term, interest rate, or any combination"
        )

    disb_je = _live_disbursement_je(db, loan.id)
    if disb_je is None:
        raise ValueError(
            "loan has no live disbursement journal entry; "
            "restore the disbursement first before editing its terms"
        )

    old_term = loan.number_of_instalments
    old_rate = Decimal(str(loan.percentage_interest or 0))
    old_amount = Decimal(str(loan.loan_amount or 0))

    if new_term_months is not None:
        try:
            term_int = int(new_term_months)
        except (TypeError, ValueError):
            raise ValueError("new_term_months must be a positive integer string")
        if term_int <= 0:
            raise ValueError("new_term_months must be positive")
        loan.number_of_instalments = str(term_int)

    if new_percentage_interest is not None:
        new_rate = Decimal(str(new_percentage_interest))
        if new_rate < 0:
            raise ValueError("new_percentage_interest cannot be negative")
        loan.percentage_interest = new_rate
    else:
        new_rate = old_rate

    if new_loan_amount is not None:
        new_amount = Decimal(str(new_loan_amount))
        if new_amount < 0:
            raise ValueError("new_loan_amount cannot be negative")
        loan.loan_amount = new_amount
    else:
        new_amount = old_amount

    old_expected = (old_amount * old_rate / Decimal("100")).quantize(Decimal("0.01"))
    new_expected = (new_amount * new_rate / Decimal("100")).quantize(Decimal("0.01"))
    interest_delta = (new_expected - old_expected).quantize(Decimal("0.01"))
    principal_delta = (new_amount - old_amount).quantize(Decimal("0.01"))

    correction_je_id = None
    if principal_delta != Decimal("0.00") or interest_delta != Decimal("0.00"):
        loans_rec = db.query(LedgerAccount).filter(
            LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
        ).first()
        bank_cash = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == "BANK_CASH"
        ).first()
        int_rec = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == "INTEREST_RECEIVABLE"
        ).first()
        int_inc = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == "INTEREST_INCOME"
        ).first()
        if principal_delta != Decimal("0.00") and (not loans_rec or not bank_cash):
            raise ValueError(
                "LOANS_RECEIVABLE or BANK_CASH ledger account missing — "
                "run scripts/setup_ledger_accounts.py"
            )
        if interest_delta != Decimal("0.00") and (not int_rec or not int_inc):
            raise ValueError(
                "INTEREST_RECEIVABLE or INTEREST_INCOME ledger account missing — "
                "run scripts/setup_ledger_accounts.py"
            )

        lines: list = []
        if principal_delta > 0:
            lines += [
                {"account_id": loans_rec.id, "debit_amount": principal_delta,
                 "credit_amount": Decimal("0.00"),
                 "description": "Adjust loan principal up (terms edited)"},
                {"account_id": bank_cash.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": principal_delta,
                 "description": "Bank cash — additional disbursement (terms edited)"},
            ]
        elif principal_delta < 0:
            amount = -principal_delta
            lines += [
                {"account_id": bank_cash.id, "debit_amount": amount,
                 "credit_amount": Decimal("0.00"),
                 "description": "Bank cash — reversal of over-disbursed principal (terms edited)"},
                {"account_id": loans_rec.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": amount,
                 "description": "Adjust loan principal down (terms edited)"},
            ]

        if interest_delta > 0:
            lines += [
                {"account_id": int_rec.id, "debit_amount": interest_delta,
                 "credit_amount": Decimal("0.00"),
                 "description": "Adjust interest receivable up (terms edited)"},
                {"account_id": int_inc.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": interest_delta,
                 "description": "Recognise additional interest income (terms edited)"},
            ]
        elif interest_delta < 0:
            amount = -interest_delta
            lines += [
                {"account_id": int_inc.id, "debit_amount": amount,
                 "credit_amount": Decimal("0.00"),
                 "description": "Un-recognise interest income (terms edited)"},
                {"account_id": int_rec.id, "debit_amount": Decimal("0.00"),
                 "credit_amount": amount,
                 "description": "Adjust interest receivable down (terms edited)"},
            ]

        if lines:
            from datetime import date as _date_cls
            disbursement_date = loan.disbursement_date or _date_cls.today()
            correction_je = create_journal_entry(
                db=db,
                description=(
                    f"Loan terms adjustment — K{old_amount}/{old_term}mo @ {old_rate}% → "
                    f"K{loan.loan_amount}/{loan.number_of_instalments}mo @ {new_rate}% "
                    f"(principal Δ={principal_delta}, interest Δ={interest_delta})"
                )[:255],
                lines=lines,
                dealing_month=get_dealing_month_date(db, loan.cycle_id, disbursement_date),
                cycle_id=loan.cycle_id,
                source_ref=str(loan.id),
                source_type="loan_terms_adjustment",
                created_by=user_id,
            )
            correction_je_id = str(correction_je.id)

    db.commit()
    return {
        "id": str(loan.id),
        "old_loan_amount": float(old_amount),
        "new_loan_amount": float(loan.loan_amount or 0),
        "old_term_months": old_term,
        "new_term_months": loan.number_of_instalments,
        "old_percentage_interest": float(old_rate),
        "new_percentage_interest": float(new_rate),
        "old_expected_interest": float(old_expected),
        "new_expected_interest": float(new_expected),
        "principal_delta": float(principal_delta),
        "interest_delta": float(interest_delta),
        "correction_journal_entry_id": correction_je_id,
        "reason": reason,
    }


def edit_loan_disbursement_date(
    db: Session,
    loan_id: UUID,
    new_disbursement_date,  # date
    reason: str,
    user_id: UUID,
) -> dict:
    """Move a loan's disbursement date — useful for retrospective loans where
    reconciliation defaulted to the approval day instead of the real disbursement.

    Updates, atomically:
      * Loan.disbursement_date
      * Loan.effective_month (kept in sync — same field on the Loan model
        used by reports for "what month did this borrowing belong to")
      * Loan.repayment_start_date / repayment_end_date if previously derived
        from disbursement_date (only recomputed when term_months is known and
        the existing values look like the old default; never overwritten if
        the treasurer set them manually to something off-grid)
      * The disbursement JE's dealing_month (the reporting bucket the
        Treasurer Loan/Revenue report groups by). entry_date is kept as the
        audit-trail timestamp.

    Repayment dates on this loan are NOT touched — those represent when
    payments actually came in.
    """
    from datetime import date as _date, datetime as _datetime
    from dateutil.relativedelta import relativedelta

    reason = _require_description(reason)

    if isinstance(new_disbursement_date, str):
        new_disbursement_date = _date.fromisoformat(new_disbursement_date)
    if not isinstance(new_disbursement_date, _date):
        raise ValueError("new_disbursement_date must be a date or YYYY-MM-DD string")

    today = _date.today()
    if new_disbursement_date > today:
        raise ValueError("disbursement date cannot be in the future")

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("loan not found")

    old_date = loan.disbursement_date
    loan.disbursement_date = new_disbursement_date
    loan.effective_month = new_disbursement_date

    # Recompute term-derived window if we previously derived it ourselves.
    if loan.number_of_instalments:
        try:
            term = int(loan.number_of_instalments)
            if old_date and loan.repayment_start_date == old_date:
                loan.repayment_start_date = new_disbursement_date
            if old_date and loan.repayment_end_date == old_date + relativedelta(months=term):
                loan.repayment_end_date = new_disbursement_date + relativedelta(months=term)
        except (ValueError, TypeError):
            pass

    # Re-bucket the disbursement JE so the Loan/Revenue report groups it
    # under the right month. entry_date stays as the real audit timestamp.
    disb_je = _live_disbursement_je(db, loan.id)
    if disb_je is not None:
        from app.services.accounting import get_dealing_month_date
        disb_je.dealing_month = get_dealing_month_date(db, loan.cycle_id, new_disbursement_date)

    db.commit()
    return {
        "id": str(loan.id),
        "old_disbursement_date": old_date.isoformat() if old_date else None,
        "new_disbursement_date": new_disbursement_date.isoformat(),
        "disbursement_journal_entry_id": str(disb_je.id) if disb_je else None,
        "reason": reason,
    }
