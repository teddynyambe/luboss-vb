"""Service layer for the payment request workflow."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ledger import LedgerAccount
from app.models.member import MemberProfile
from app.models.payment_request import (
    ALLOWED_SOURCE_ACCOUNTS,
    PaymentCategory,
    PaymentRequest,
    PaymentRequestStatus,
)
from app.models.user import User
from app.services.accounting import create_journal_entry, get_account_balance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_source_account(db: Session, code: str) -> LedgerAccount:
    """Look up an org-level ledger account by code."""
    acc = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == code,
        LedgerAccount.member_id.is_(None),
    ).first()
    if not acc:
        raise ValueError(f"Ledger account '{code}' not found")
    return acc


def _user_display_name(user: User) -> str:
    return f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() or user.email


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_payment_request(
    db: Session,
    *,
    amount: Decimal,
    description: str,
    source_account_code: str,
    beneficiary_name: str,
    cycle_id: Optional[UUID],
    initiated_by: UUID,
) -> PaymentRequest:
    """Create a new payment request (Step 1 — Vice-Chairman / Chairman).

    The person raising the expense picks one of the allowed source accounts
    (Admin Fund, Social Fund, Savings + Interest, Penalties) and describes
    what the expense is for.
    """
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")

    if source_account_code not in ALLOWED_SOURCE_ACCOUNTS:
        raise ValueError(
            f"Invalid source account '{source_account_code}'. "
            f"Allowed: {', '.join(ALLOWED_SOURCE_ACCOUNTS.keys())}"
        )

    # Validate the source account exists in the ledger
    _resolve_source_account(db, source_account_code)

    pr = PaymentRequest(
        amount=amount,
        description=description,
        category=PaymentCategory.GENERAL_EXPENSE,
        source_account_code=source_account_code,
        beneficiary_name=beneficiary_name,
        beneficiary_member_id=None,
        cycle_id=cycle_id,
        status=PaymentRequestStatus.PENDING,
        initiated_by=initiated_by,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)

    from app.core.audit import write_audit_log
    initiator = db.query(User).filter(User.id == initiated_by).first()
    write_audit_log(
        user_name=_user_display_name(initiator) if initiator else "Unknown",
        user_role="vice-chairman",
        action="Payment request created",
        details=f"amount=K{amount:,.2f}, source={source_account_code}, beneficiary={beneficiary_name}, description={description}",
    )

    logger.info("Payment request %s created by %s", pr.id, initiated_by)
    return pr


# ---------------------------------------------------------------------------
# Approve / Reject  (Step 2 — Chairman)
# ---------------------------------------------------------------------------

def approve_payment_request(
    db: Session,
    request_id: UUID,
    approver_user_id: UUID,
) -> PaymentRequest:
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not pr:
        raise ValueError("Payment request not found")
    if pr.status != PaymentRequestStatus.PENDING:
        raise ValueError(f"Cannot approve a request with status '{pr.status.value}'")

    pr.status = PaymentRequestStatus.APPROVED
    pr.approved_by = approver_user_id
    pr.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(pr)

    from app.core.audit import write_audit_log
    approver = db.query(User).filter(User.id == approver_user_id).first()
    write_audit_log(
        user_name=_user_display_name(approver) if approver else "Unknown",
        user_role="chairman",
        action="Payment request approved",
        details=f"id={pr.id}, amount=K{pr.amount:,.2f}, beneficiary={pr.beneficiary_name}",
    )
    return pr


def reject_payment_request(
    db: Session,
    request_id: UUID,
    approver_user_id: UUID,
    rejection_reason: str,
) -> PaymentRequest:
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not pr:
        raise ValueError("Payment request not found")
    if pr.status != PaymentRequestStatus.PENDING:
        raise ValueError(f"Cannot reject a request with status '{pr.status.value}'")

    pr.status = PaymentRequestStatus.REJECTED
    pr.approved_by = approver_user_id
    pr.approved_at = datetime.utcnow()
    pr.rejection_reason = rejection_reason
    db.commit()
    db.refresh(pr)

    from app.core.audit import write_audit_log
    approver = db.query(User).filter(User.id == approver_user_id).first()
    write_audit_log(
        user_name=_user_display_name(approver) if approver else "Unknown",
        user_role="chairman",
        action="Payment request rejected",
        details=f"id={pr.id}, reason={rejection_reason}",
    )
    return pr


# ---------------------------------------------------------------------------
# Execute  (Step 3 — Treasurer)
# ---------------------------------------------------------------------------

def execute_payment_request(
    db: Session,
    request_id: UUID,
    executor_user_id: UUID,
    payment_reference: Optional[str] = None,
) -> PaymentRequest:
    """Execute an approved payment request — posts the journal entry and
    deducts from the source account."""
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not pr:
        raise ValueError("Payment request not found")
    if pr.status != PaymentRequestStatus.APPROVED:
        raise ValueError(f"Cannot execute a request with status '{pr.status.value}'")

    amount = Decimal(str(pr.amount))

    # Resolve source and bank cash accounts
    source_acc = _resolve_source_account(db, pr.source_account_code)
    bank_acc = _resolve_source_account(db, "BANK_CASH")

    # Journal entry: debit source account, credit bank cash
    description = f"Payment: {pr.description} — {pr.beneficiary_name}"
    lines = [
        {"account_id": source_acc.id, "debit_amount": amount, "credit_amount": Decimal("0"), "description": description},
        {"account_id": bank_acc.id,   "debit_amount": Decimal("0"), "credit_amount": amount, "description": description},
    ]

    journal_entry = create_journal_entry(
        db=db,
        description=description,
        lines=lines,
        cycle_id=pr.cycle_id,
        source_ref=str(pr.id),
        source_type="payment_request",
        created_by=executor_user_id,
    )

    pr.status = PaymentRequestStatus.EXECUTED
    pr.executed_by = executor_user_id
    pr.executed_at = datetime.utcnow()
    pr.journal_entry_id = journal_entry.id
    pr.payment_reference = payment_reference
    db.commit()
    db.refresh(pr)

    from app.core.audit import write_audit_log
    executor = db.query(User).filter(User.id == executor_user_id).first()
    write_audit_log(
        user_name=_user_display_name(executor) if executor else "Unknown",
        user_role="treasurer",
        action="Payment request executed",
        details=f"id={pr.id}, amount=K{pr.amount:,.2f}, beneficiary={pr.beneficiary_name}, ref={payment_reference or 'N/A'}",
    )
    return pr


# ---------------------------------------------------------------------------
# Cancel  (only PENDING, only by initiator)
# ---------------------------------------------------------------------------

def cancel_payment_request(
    db: Session,
    request_id: UUID,
    user_id: UUID,
) -> PaymentRequest:
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not pr:
        raise ValueError("Payment request not found")
    if pr.status != PaymentRequestStatus.PENDING:
        raise ValueError("Only pending requests can be cancelled")
    if pr.initiated_by != user_id:
        raise ValueError("Only the initiator can cancel this request")

    pr.status = PaymentRequestStatus.CANCELLED
    db.commit()
    db.refresh(pr)
    return pr


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def get_payment_requests(
    db: Session,
    *,
    status_filter: Optional[PaymentRequestStatus] = None,
    initiated_by: Optional[UUID] = None,
) -> List[PaymentRequest]:
    q = db.query(PaymentRequest)
    if status_filter:
        q = q.filter(PaymentRequest.status == status_filter)
    if initiated_by:
        q = q.filter(PaymentRequest.initiated_by == initiated_by)
    return q.order_by(PaymentRequest.initiated_at.desc()).all()
