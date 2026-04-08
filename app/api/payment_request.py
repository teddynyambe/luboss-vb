"""API router for the Payment Request / Expense workflow.

Workflow:  Vice-Chairman creates → Chairman approves → Treasurer executes.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    require_any_role,
    require_chairman,
    require_treasurer,
)
from app.db.base import get_db
from app.models.payment_request import PaymentRequestStatus
from app.models.user import User
from app.schemas.payment_request import (
    PaymentRequestCreate,
    PaymentRequestExecute,
    PaymentRequestReject,
    PaymentRequestResponse,
)
from app.services.payment_request import (
    approve_payment_request,
    cancel_payment_request,
    create_payment_request,
    execute_payment_request,
    get_payment_requests,
    reject_payment_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment-requests", tags=["payment-requests"])


def _user_name(user: User) -> str:
    return f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() or user.email


def _enrich(pr, db: Session) -> dict:
    """Turn a PaymentRequest ORM object into a response dict with user names."""
    data = {
        "id": pr.id,
        "amount": pr.amount,
        "description": pr.description,
        "category": pr.category,
        "source_account_code": pr.source_account_code,
        "beneficiary_name": pr.beneficiary_name,
        "beneficiary_member_id": pr.beneficiary_member_id,
        "cycle_id": pr.cycle_id,
        "status": pr.status,
        "initiated_by": pr.initiated_by,
        "initiated_at": pr.initiated_at,
        "approved_by": pr.approved_by,
        "approved_at": pr.approved_at,
        "rejection_reason": pr.rejection_reason,
        "executed_by": pr.executed_by,
        "executed_at": pr.executed_at,
        "payment_reference": pr.payment_reference,
        "journal_entry_id": pr.journal_entry_id,
    }
    # Resolve names
    for field, fk in [("initiator_name", pr.initiated_by),
                      ("approver_name", pr.approved_by),
                      ("executor_name", pr.executed_by)]:
        if fk:
            u = db.query(User).filter(User.id == fk).first()
            data[field] = _user_name(u) if u else None
        else:
            data[field] = None
    return data


# ---------------------------------------------------------------------------
# Create (Vice-Chairman or Chairman)
# ---------------------------------------------------------------------------

@router.post("/", response_model=PaymentRequestResponse)
def create_request(
    body: PaymentRequestCreate,
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman")),
    db: Session = Depends(get_db),
):
    try:
        pr = create_payment_request(
            db,
            amount=body.amount,
            description=body.description,
            category=body.category,
            beneficiary_name=body.beneficiary_name,
            beneficiary_member_id=body.beneficiary_member_id,
            cycle_id=body.cycle_id,
            initiated_by=current_user.id,
        )
        return _enrich(pr, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# List (Vice-Chairman, Chairman, Treasurer)
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[PaymentRequestResponse])
def list_requests(
    status: Optional[str] = None,
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman", "Treasurer")),
    db: Session = Depends(get_db),
):
    status_enum = None
    if status:
        try:
            status_enum = PaymentRequestStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    requests = get_payment_requests(db, status_filter=status_enum)
    return [_enrich(pr, db) for pr in requests]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/{request_id}", response_model=PaymentRequestResponse)
def get_request(
    request_id: UUID,
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman", "Treasurer")),
    db: Session = Depends(get_db),
):
    from app.models.payment_request import PaymentRequest
    pr = db.query(PaymentRequest).filter(PaymentRequest.id == request_id).first()
    if not pr:
        raise HTTPException(status_code=404, detail="Payment request not found")
    return _enrich(pr, db)


# ---------------------------------------------------------------------------
# Approve (Chairman only)
# ---------------------------------------------------------------------------

@router.put("/{request_id}/approve", response_model=PaymentRequestResponse)
def approve_request(
    request_id: UUID,
    current_user: User = Depends(require_chairman),
    db: Session = Depends(get_db),
):
    try:
        pr = approve_payment_request(db, request_id, current_user.id)
        return _enrich(pr, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Reject (Chairman only)
# ---------------------------------------------------------------------------

@router.put("/{request_id}/reject", response_model=PaymentRequestResponse)
def reject_request(
    request_id: UUID,
    body: PaymentRequestReject,
    current_user: User = Depends(require_chairman),
    db: Session = Depends(get_db),
):
    try:
        pr = reject_payment_request(db, request_id, current_user.id, body.rejection_reason)
        return _enrich(pr, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Execute (Treasurer only)
# ---------------------------------------------------------------------------

@router.put("/{request_id}/execute", response_model=PaymentRequestResponse)
def execute_request(
    request_id: UUID,
    body: PaymentRequestExecute,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    try:
        pr = execute_payment_request(
            db, request_id, current_user.id, body.payment_reference,
        )
        return _enrich(pr, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Cancel (only initiator, only PENDING)
# ---------------------------------------------------------------------------

@router.put("/{request_id}/cancel", response_model=PaymentRequestResponse)
def cancel_request(
    request_id: UUID,
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman")),
    db: Session = Depends(get_db),
):
    try:
        pr = cancel_payment_request(db, request_id, current_user.id)
        return _enrich(pr, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
