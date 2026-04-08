"""API router for the Payment Request / Expense workflow.

Workflow:  Vice-Chairman creates → Chairman approves → Treasurer executes.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    require_any_role,
    require_chairman,
    require_treasurer,
)
from app.db.base import get_db
from app.models.payment_request import PaymentCategory, PaymentRequest as PaymentRequestModel, PaymentRequestStatus
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

from app.models.ledger import LedgerAccount
from app.services.accounting import get_account_balance

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
# Account balances (for the create form dropdown)
# ---------------------------------------------------------------------------

@router.get("/account-balances")
def get_account_balances(
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman", "Treasurer")),
    db: Session = Depends(get_db),
):
    """Return current balances for the fund accounts used as payment sources."""
    codes = ["ADMIN_FUND", "SOCIAL_FUND", "BANK_CASH"]
    result = {}
    for code in codes:
        acc = db.query(LedgerAccount).filter(
            LedgerAccount.account_code == code,
            LedgerAccount.member_id.is_(None),
        ).first()
        if acc:
            result[code] = float(get_account_balance(db, acc.id))
        else:
            result[code] = 0.0
    return result


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


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/reports/summary")
def report_summary(
    month: Optional[str] = Query(None, description="YYYY-MM-DD (first of month)"),
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman", "Treasurer")),
    db: Session = Depends(get_db),
):
    """Monthly summary of payment requests — totals by status and category."""
    q = db.query(PaymentRequestModel)

    if month:
        try:
            target = datetime.strptime(month, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")
        q = q.filter(
            extract("year", PaymentRequestModel.initiated_at) == target.year,
            extract("month", PaymentRequestModel.initiated_at) == target.month,
        )

    requests = q.order_by(PaymentRequestModel.initiated_at.desc()).all()

    # Totals by status
    by_status: dict = {}
    for pr in requests:
        s = pr.status.value
        by_status.setdefault(s, {"count": 0, "total": Decimal("0")})
        by_status[s]["count"] += 1
        by_status[s]["total"] += pr.amount
    for v in by_status.values():
        v["total"] = float(v["total"])

    # Totals by category
    by_category: dict = {}
    for pr in requests:
        c = pr.category.value
        by_category.setdefault(c, {"count": 0, "total": Decimal("0")})
        by_category[c]["count"] += 1
        by_category[c]["total"] += pr.amount
    for v in by_category.values():
        v["total"] = float(v["total"])

    total_amount = float(sum(pr.amount for pr in requests))
    executed_amount = float(sum(pr.amount for pr in requests if pr.status == PaymentRequestStatus.EXECUTED))

    return {
        "month": month,
        "total_requests": len(requests),
        "total_amount": total_amount,
        "executed_amount": executed_amount,
        "by_status": by_status,
        "by_category": by_category,
    }


@router.get("/reports/transactions")
def report_transactions(
    month: Optional[str] = Query(None, description="YYYY-MM-DD (first of month)"),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_any_role("Vice-Chairman", "Chairman", "Treasurer")),
    db: Session = Depends(get_db),
):
    """Detailed transaction list with full audit trail for each payment request."""
    q = db.query(PaymentRequestModel)

    if month:
        try:
            target = datetime.strptime(month, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")
        q = q.filter(
            extract("year", PaymentRequestModel.initiated_at) == target.year,
            extract("month", PaymentRequestModel.initiated_at) == target.month,
        )

    if category:
        try:
            cat_enum = PaymentCategory(category)
            q = q.filter(PaymentRequestModel.category == cat_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    if status:
        try:
            status_enum = PaymentRequestStatus(status)
            q = q.filter(PaymentRequestModel.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    requests = q.order_by(PaymentRequestModel.initiated_at.desc()).all()

    transactions = []
    for pr in requests:
        transactions.append(_enrich(pr, db))

    total = float(sum(pr.amount for pr in requests))

    return {
        "month": month,
        "filters": {"category": category, "status": status},
        "count": len(transactions),
        "total_amount": total,
        "transactions": transactions,
    }
