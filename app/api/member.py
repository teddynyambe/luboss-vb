from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_member, get_current_user, require_not_admin
from app.models.user import User
from app.models.member import MemberProfile, MemberStatus
from app.models.transaction import Declaration, DeclarationStatus, DepositProof, DepositProofStatus, LoanApplication, LoanApplicationStatus, Loan, LoanStatus, DepositApproval, BankStatement, Repayment, PenaltyRecord, PenaltyRecordStatus, PenaltyType
from app.services.member import get_member_profile_by_user_id
from app.services.transaction import create_declaration, update_declaration
from app.services.accounting import (
    get_member_savings_balance,
    get_member_loan_balance,
    get_member_social_fund_balance,
    get_member_admin_fund_balance,
    get_member_penalties_balance,
    get_member_social_fund_payments,
    get_member_admin_fund_payments,
    get_member_monthly_loan_balances,
)
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from uuid import UUID
import uuid
import os
from pathlib import Path
from app.core.config import DEPOSIT_PROOFS_DIR

router = APIRouter(prefix="/api/member", tags=["member"])


class DeclarationCreate(BaseModel):
    cycle_id: str
    effective_month: date
    declared_savings_amount: Optional[float] = None
    declared_social_fund: Optional[float] = None
    declared_admin_fund: Optional[float] = None
    declared_penalties: Optional[float] = None
    declared_interest_on_loan: Optional[float] = None
    declared_loan_repayment: Optional[float] = None


class LoanApplicationCreate(BaseModel):
    cycle_id: str
    amount: float
    term_months: str
    notes: Optional[str] = None
    borrowing_date: Optional[str] = None  # ISO YYYY-MM-DD; sets application_date on the record


@router.get("/todos")
def get_member_todos(
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db),
):
    """Ordered to-do list of pending actions for the member.

    Ordered by the group's monthly lifecycle:
      1. Declare for the current month (if missing)
      2. Revise rejected declarations (any month)
      3. Submit Proof of Payment (PoP) for the current month declaration
      4. Resubmit rejected PoP (any past month)
      5. Submit any missing PoP for past declarations of any status (covers the
         "0 amounts" case where a declaration is approved but no PoP was ever
         uploaded)

    Past months with no declaration at all are intentionally skipped — the
    list is for items the member needs to act on, not historical gaps.
    """
    from datetime import date as _date
    from app.models.transaction import (
        Declaration, DeclarationStatus, DepositProof, DepositProofStatus,
    )

    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return {"todos": [], "count": 0}

    today = _date.today()
    current_month = _date(today.year, today.month, 1)
    current_month_label = today.strftime("%B %Y")

    # Pull everything once, group in Python — small per-member volumes.
    declarations = (
        db.query(Declaration)
        .filter(Declaration.member_id == member_profile.id)
        .order_by(Declaration.effective_month.desc())
        .all()
    )
    proofs = (
        db.query(DepositProof)
        .filter(DepositProof.member_id == member_profile.id)
        .all()
    )
    proofs_by_declaration: dict = {}
    for p in proofs:
        if p.declaration_id:
            proofs_by_declaration.setdefault(str(p.declaration_id), []).append(p)

    def _has_live_proof(decl_id: str) -> bool:
        # A "live" proof is one that's either pending treasurer review (SUBMITTED)
        # or already approved — both block the member from re-uploading.
        for p in proofs_by_declaration.get(decl_id, []):
            if p.status in (DepositProofStatus.SUBMITTED.value, DepositProofStatus.APPROVED.value):
                return True
        return False

    def _has_rejected_proof(decl_id: str) -> bool:
        return any(
            p.status == DepositProofStatus.REJECTED.value
            for p in proofs_by_declaration.get(decl_id, [])
        )

    todos: list[dict] = []

    # 1. Declare for current month? Only surface when the declaration window
    #    is actually open. The window runs from the 15th of the current month
    #    through the 5th of the next month — same convention as the
    #    declarations page and as `_can_edit_declaration`. Outside that range,
    #    prompting a member to declare is misleading.
    #
    #    (Note: the cycle_phase model has `monthly_start_day` / `monthly_end_day`
    #    fields but they're used for dealing-month / reporting-bucket logic
    #    elsewhere, not for the declaration window. Hardcoding here keeps the
    #    member-facing prompts consistent with the form's own gating.)
    window_open = _date(today.year, today.month, 15)
    if today.month == 12:
        window_close = _date(today.year + 1, 1, 5)
    else:
        window_close = _date(today.year, today.month + 1, 5)
    declaration_window_open = window_open <= today <= window_close

    current_month_decl = next(
        (d for d in declarations
         if d.effective_month.year == today.year and d.effective_month.month == today.month),
        None,
    )
    if current_month_decl is None and declaration_window_open:
        todos.append({
            "kind": "declare_current_month",
            "priority": 1,
            "title": f"Make your {current_month_label} declaration",
            "description": (
                f"The declaration window is open until "
                f"{window_close.strftime('%-d %B %Y')}. Declare your savings, "
                "contributions and any loan repayments."
            ),
            "link": "/dashboard/member/declarations",
            "effective_month": current_month.isoformat(),
        })

    # 2. Revise rejected declarations (any month)
    for d in declarations:
        if d.status == DeclarationStatus.REJECTED:
            todos.append({
                "kind": "repair_rejected_declaration",
                "priority": 2,
                "title": f"Revise {d.effective_month.strftime('%B %Y')} declaration",
                "description": "This declaration was rejected and needs revision.",
                "link": f"/dashboard/member/declarations?edit={d.id}&tab=create",
                "declaration_id": str(d.id),
                "effective_month": d.effective_month.isoformat(),
            })

    # 3. Submit PoP for current month declaration (if it exists and has no live proof)
    if current_month_decl and not _has_live_proof(str(current_month_decl.id)):
        todos.append({
            "kind": "submit_pop_current_month",
            "priority": 3,
            "title": f"Submit Proof of Payment for {current_month_label}",
            "description": "Your declaration is recorded — upload your proof of payment to complete it.",
            "link": f"/dashboard/member/payment-proof?declaration={current_month_decl.id}",
            "declaration_id": str(current_month_decl.id),
            "effective_month": current_month_decl.effective_month.isoformat(),
        })

    # PoP-related items below only fire when the member genuinely committed
    # to a declaration: status PROOF (PoP submitted, possibly rejected by
    # treasurer) or APPROVED (declaration accepted, but file may be missing).
    # PENDING declarations skip here — those are "draft" states; if revision
    # is needed they should go through item 2 once treasurer rejects them.
    # REJECTED declarations also skip — those need the declaration itself
    # revised (item 2) before any new PoP is meaningful. This matches the
    # policy that retrospective declarations are not allowed: if the member
    # didn't actually commit, no PoP follow-up should be surfaced.
    PoP_RELEVANT_STATUSES = (DeclarationStatus.PROOF, DeclarationStatus.APPROVED)

    # 4. Resubmit rejected PoP — past declarations in PROOF/APPROVED status
    #    with a REJECTED proof and no subsequent live one. Skip current month.
    for d in declarations:
        if d.effective_month.year == today.year and d.effective_month.month == today.month:
            continue
        if d.status not in PoP_RELEVANT_STATUSES:
            continue
        decl_id = str(d.id)
        if _has_rejected_proof(decl_id) and not _has_live_proof(decl_id):
            todos.append({
                "kind": "repair_rejected_pop",
                "priority": 4,
                "title": f"Resubmit Proof of Payment for {d.effective_month.strftime('%B %Y')}",
                "description": "Your previous proof of payment was rejected. Upload a corrected one.",
                "link": f"/dashboard/member/payment-proof?declaration={d.id}",
                "declaration_id": decl_id,
                "effective_month": d.effective_month.isoformat(),
            })

    # 5. Submit missing PoP — APPROVED-but-no-PoP "0 amounts" case. Only fires
    #    for APPROVED declarations specifically: that's the state where the
    #    declaration is on the books but no proof was ever uploaded. PROOF
    #    status already has *something* on file, so it won't surface here.
    surfaced_ids = {t.get("declaration_id") for t in todos if t.get("declaration_id")}
    for d in declarations:
        if d.effective_month.year == today.year and d.effective_month.month == today.month:
            continue
        if d.status != DeclarationStatus.APPROVED:
            continue
        decl_id = str(d.id)
        if decl_id in surfaced_ids:
            continue
        if proofs_by_declaration.get(decl_id):
            continue  # has some proof — handled by items 3 or 4
        todos.append({
            "kind": "submit_unsubmitted_pop",
            "priority": 5,
            "title": f"Submit Proof of Payment for {d.effective_month.strftime('%B %Y')}",
            "description": "This approved declaration has no proof of payment on file.",
            "link": f"/dashboard/member/payment-proof?declaration={d.id}",
            "declaration_id": decl_id,
            "effective_month": d.effective_month.isoformat(),
        })

    # Stable sort: by priority first, then by effective_month descending so
    # the most recent rejected items rise to the top within each priority.
    todos.sort(key=lambda t: (t["priority"], t.get("effective_month") or ""), reverse=False)
    # Within each priority, flip month so newer first (priority kept ascending).
    todos.sort(key=lambda t: (t["priority"], -1 * int((t.get("effective_month") or "0000-00-00").replace("-", ""))))

    return {"todos": todos, "count": len(todos)}


@router.get("/reports/interest-revenue")
def get_member_interest_revenue_report(
    cycle_id: Optional[str] = None,
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db),
):
    """Group-wide loan / interest-revenue report — same shape and content as
    the treasurer's report. Exposed to members so they can see how the group
    is performing (transparency)."""
    from app.services.interest_revenue_report import get_interest_revenue_report
    return get_interest_revenue_report(db, cycle_id=cycle_id)


@router.get("/status")
def get_my_status(
    as_of_month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get my account status (savings, loans, penalties summary).

    `as_of_month` (optional, ISO YYYY-MM-DD): compute outstanding loan and
    interest-due as-of that month rather than today. Used by the declarations
    page when editing a past declaration, so the form only reflects loans that
    existed at the time and repayments made up to that point.
    """
    # Parse as_of_month into a date cutoff (last day of the month makes the
    # comparison inclusive of repayments dated within that month).
    as_of_cutoff = None
    if as_of_month:
        try:
            from calendar import monthrange
            base = date.fromisoformat(as_of_month)
            last_day = monthrange(base.year, base.month)[1]
            as_of_cutoff = date(base.year, base.month, last_day)
        except (ValueError, TypeError):
            as_of_cutoff = None
    try:
        member_profile = get_member_profile_by_user_id(db, current_user.id)
        if not member_profile:
            # Return placeholder data instead of 404
            return {
                "member_id": None,
                "savings_balance": 0.0,
                "loan_balance": 0.0,
                "social_fund_balance": 0.0,
                "admin_fund_balance": 0.0,
                "penalties_balance": 0.0,
                "total_loans_count": 0,
                "pending_penalties_count": 0,
                "message": "To be done - member profile not found"
            }
        
        if member_profile.status != MemberStatus.ACTIVE:
            # Return placeholder data instead of 403
            return {
                "member_id": str(member_profile.id),
                "savings_balance": 0.0,
                "loan_balance": 0.0,
                "social_fund_balance": 0.0,
                "admin_fund_balance": 0.0,
                "penalties_balance": 0.0,
                "total_loans_count": 0,
                "pending_penalties_count": 0,
                "message": "To be done - member account not active"
            }
        
        # Get active cycle to check fund requirements
        from app.models.cycle import Cycle, CycleStatus
        active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
        social_fund_required = active_cycle.social_fund_required if active_cycle and active_cycle.social_fund_required else None
        admin_fund_required = active_cycle.admin_fund_required if active_cycle and active_cycle.admin_fund_required else None
        
        # Get balances from ledger
        try:
            savings_balance = get_member_savings_balance(db, member_profile.id)
            # When the caller is asking about a past month (editing a past
            # declaration), compute outstanding as-of the end of that month so
            # loans disbursed AFTER that month don't contaminate the figure.
            if as_of_cutoff:
                from datetime import datetime as _dt
                loan_balance = get_member_loan_balance(
                    db, member_profile.id,
                    as_of_date=_dt.combine(as_of_cutoff, _dt.min.time()),
                )
            else:
                loan_balance = get_member_loan_balance(db, member_profile.id)
            # For Account Status display, show accumulated payments (not balance due)
            social_fund_balance = get_member_social_fund_payments(db, member_profile.id)
            admin_fund_balance = get_member_admin_fund_payments(db, member_profile.id)
            penalties_balance = get_member_penalties_balance(db, member_profile.id)
        except Exception:
            savings_balance = Decimal("0.0")
            loan_balance = Decimal("0.0")
            social_fund_balance = Decimal("0.0")
            admin_fund_balance = Decimal("0.0")
            penalties_balance = Decimal("0.0")
        
        # Get total loans count (all loans taken by member)
        try:
            total_loans = db.query(Loan).filter(
                Loan.member_id == member_profile.id
            ).count()
        except Exception:
            total_loans = 0
        
        # Get pending penalties count
        try:
            from app.models.transaction import PenaltyRecord, PenaltyRecordStatus
            pending_penalties_count = db.query(PenaltyRecord).filter(
                PenaltyRecord.member_id == member_profile.id,
                PenaltyRecord.status == PenaltyRecordStatus.PENDING
            ).count()
        except Exception:
            pending_penalties_count = 0

        # Monthly interest due on active loans (minus interest already paid).
        # Interest paid is sourced from Repayment rows (same source as the ledger
        # statement), so Payment-Proof and Reconciliation paths agree.
        try:
            from app.models.transaction import LoanStatus as _LS, Repayment
            from app.models.ledger import JournalEntry as _JE
            from sqlalchemy import func as _func
            # As-of-month: include OPEN/DISBURSED loans whose disbursement
            # happened on or before the cutoff. Same logic as the loan-balance
            # calc — closed loans are excluded because they were paid off (a
            # closed loan with stale-data interest would otherwise show up).
            if as_of_cutoff:
                loan_q = db.query(Loan).filter(
                    Loan.member_id == member_profile.id,
                    Loan.loan_status.in_([_LS.OPEN, _LS.DISBURSED]),
                    Loan.disbursement_date.isnot(None),
                    Loan.disbursement_date <= as_of_cutoff,
                )
            else:
                loan_q = db.query(Loan).filter(
                    Loan.member_id == member_profile.id,
                    Loan.loan_status.in_([_LS.OPEN, _LS.DISBURSED]),
                )
            active_loans = loan_q.all()
            interest_on_loan_due = 0.0
            for loan in active_loans:
                monthly_interest = float(loan.loan_amount) * float(loan.percentage_interest) / 100
                paid_q = (
                    db.query(_func.coalesce(_func.sum(Repayment.interest_amount), 0))
                    .join(_JE, _JE.id == Repayment.journal_entry_id)
                    .filter(
                        Repayment.loan_id == loan.id,
                        _JE.reversed_by.is_(None),
                        _JE.reversed_at.is_(None),
                    )
                )
                if as_of_cutoff:
                    paid_q = paid_q.filter(Repayment.repayment_date <= as_of_cutoff)
                total_interest_paid = float(paid_q.scalar() or 0)
                interest_on_loan_due += max(0.0, monthly_interest - total_interest_paid)
        except Exception:
            interest_on_loan_due = 0.0

        return {
            "member_id": str(member_profile.id),
            "savings_balance": float(savings_balance),
            "loan_balance": float(loan_balance),
            "social_fund_balance": float(social_fund_balance),
            "social_fund_required": float(social_fund_required) if social_fund_required else None,
            "admin_fund_balance": float(admin_fund_balance),
            "admin_fund_required": float(admin_fund_required) if admin_fund_required else None,
            "penalties_balance": float(penalties_balance),
            "interest_on_loan_due": interest_on_loan_due,
            "total_loans_count": total_loans,
            "pending_penalties_count": pending_penalties_count
        }
    except Exception as e:
        # Return placeholder data on any error
        return {
            "member_id": None,
            "savings_balance": 0.0,
            "loan_balance": 0.0,
            "social_fund_balance": 0.0,
            "admin_fund_balance": 0.0,
            "penalties_balance": 0.0,
            "total_loans_count": 0,
            "pending_penalties_count": 0,
            "message": f"To be done - {str(e)}"
        }


@router.post("/declarations")
def create_declaration_endpoint(
    declaration_data: DeclarationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a declaration. All authenticated users can make declarations."""
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(
            status_code=403,
            detail="Member profile not found. Please contact administrator to set up your member profile."
        )
    if member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail=f"Member account is not active. Current status: {member_profile.status.value}"
        )

    # ── Enforce declaration window: 15th of the month to 5th of the next month ──
    today = date.today()
    eff = declaration_data.effective_month
    # Determine the valid window for the declared effective month
    window_open  = date(eff.year, eff.month, 15)
    if eff.month == 12:
        window_close = date(eff.year + 1, 1, 5)
    else:
        window_close = date(eff.year, eff.month + 1, 5)
    if not (window_open <= today <= window_close):
        raise HTTPException(
            status_code=400,
            detail=f"Declarations for {eff.strftime('%B %Y')} can only be made between "
                   f"{window_open.strftime('%d %B %Y')} and {window_close.strftime('%d %B %Y')}."
        )

    try:
        declaration = create_declaration(
            db=db,
            member_id=member_profile.id,
            cycle_id=declaration_data.cycle_id,
            effective_month=declaration_data.effective_month,
            declared_savings_amount=Decimal(str(declaration_data.declared_savings_amount)) if declaration_data.declared_savings_amount is not None else None,
            declared_social_fund=Decimal(str(declaration_data.declared_social_fund)) if declaration_data.declared_social_fund is not None else None,
            declared_admin_fund=Decimal(str(declaration_data.declared_admin_fund)) if declaration_data.declared_admin_fund is not None else None,
            declared_penalties=Decimal(str(declaration_data.declared_penalties)) if declaration_data.declared_penalties is not None else None,
            declared_interest_on_loan=Decimal(str(declaration_data.declared_interest_on_loan)) if declaration_data.declared_interest_on_loan is not None else None,
            declared_loan_repayment=Decimal(str(declaration_data.declared_loan_repayment)) if declaration_data.declared_loan_repayment is not None else None
        )
        from app.core.audit import write_audit_log
        write_audit_log(
            user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
            user_role=current_user.role.value if current_user.role else "member",
            action="Declaration submitted",
            details=f"month={declaration_data.effective_month.strftime('%Y-%m')}"
        )
        return {"message": "Declaration created successfully", "declaration_id": str(declaration.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cycles")
def get_active_cycles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get active cycles available for declarations and loan applications."""
    from app.models.cycle import Cycle, CycleStatus
    from sqlalchemy import or_
    import logging
    
    try:
        # Query for active cycles - handle both enum and string comparison
        # SQLAlchemy enum columns can be compared directly with the enum value
        cycles = db.query(Cycle).filter(
            Cycle.status == CycleStatus.ACTIVE
        ).order_by(Cycle.year.desc()).all()
        
        # If no cycles found with enum, try string comparison as fallback
        if not cycles:
            cycles = db.query(Cycle).filter(
                Cycle.status == "active"
            ).order_by(Cycle.year.desc()).all()
        
        logging.info(f"Found {len(cycles)} active cycles for user {current_user.id}")
        
        result = [
            {
                "id": str(cycle.id),
                "year": cycle.year,
                "cycle_number": 1,  # Default, can be enhanced
                "start_date": cycle.start_date.isoformat(),
                "end_date": cycle.end_date.isoformat() if cycle.end_date else None,
                "status": cycle.status.value if hasattr(cycle.status, 'value') else str(cycle.status)
            }
            for cycle in cycles
        ]
        
        logging.info(f"Returning {len(result)} cycles")
        return result
    except Exception as e:
        # Log error and return empty list
        logging.error(f"Error fetching active cycles: {str(e)}", exc_info=True)
        import traceback
        logging.error(traceback.format_exc())
        return []


@router.get("/penalties/pending")
def get_pending_penalties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pending penalties for the current member."""
    from app.models.transaction import PenaltyRecord, PenaltyRecordStatus
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return {"total_amount": 0.0, "penalties": []}
    
    # Get all pending penalties for this member (only PENDING status)
    pending_penalties = db.query(PenaltyRecord).filter(
        PenaltyRecord.member_id == member_profile.id,
        PenaltyRecord.status == PenaltyRecordStatus.PENDING
    ).all()
    
    total_amount = Decimal("0.00")
    penalties_list = []
    
    for penalty in pending_penalties:
        # Get penalty type to get fee amount
        penalty_type = penalty.penalty_type
        fee_amount = penalty_type.fee_amount if penalty_type else Decimal("0.00")
        total_amount += fee_amount
        
        penalties_list.append({
            "id": str(penalty.id),
            "penalty_type_name": penalty_type.name if penalty_type else "Unknown",
            "fee_amount": float(fee_amount),
            "date_issued": penalty.date_issued.isoformat() if penalty.date_issued else None,
            "notes": penalty.notes
        })
    
    return {
        "total_amount": float(total_amount),
        "penalties": penalties_list
    }


@router.get("/my-penalties")
def get_my_penalties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Full penalty history for the CURRENT member — every status,
    newest first. Mirrors the compliance dashboard's per-member audit
    but scoped to the caller so the member can see (in the Penalties
    modal from their dashboard) exactly why they were charged, when,
    and the current status of every penalty.

    Reuses the narration in ``PenaltyRecord.notes`` (which now carries
    the ISO 8601 offending timestamp + the missed window). Timestamps
    are returned as ISO 8601 UTC — the frontend re-renders them in the
    browser's local timezone.
    """
    from app.models.transaction import (
        PenaltyRecord, PenaltyRecordStatus, PenaltyType,
    )
    from app.services.transaction import (
        is_reconciliation_declaration_for_member_month,
        _extract_effective_month_from_notes,
    )
    from datetime import date as _date

    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return {
            "member_id": None,
            "summary": {
                "total_count": 0,
                "pending_count": 0,
                "approved_count": 0,
                "reversal_pending_count": 0,
                "reversed_count": 0,
                "paid_count": 0,
                "total_owed": 0.0,
            },
            "penalties": [],
        }

    penalties = (
        db.query(PenaltyRecord)
        .filter(PenaltyRecord.member_id == member_profile.id)
        .order_by(PenaltyRecord.date_issued.desc())
        .all()
    )

    summary = {
        "total_count": len(penalties),
        "pending_count": 0,
        "approved_count": 0,
        "reversal_pending_count": 0,
        "reversed_count": 0,
        "paid_count": 0,
        "total_owed": 0.0,
    }

    rows = []
    for p in penalties:
        ptype = p.penalty_type
        fee = float(ptype.fee_amount) if ptype and ptype.fee_amount is not None else 0.0
        status_val = p.status.value if isinstance(p.status, PenaltyRecordStatus) else p.status

        if status_val == PenaltyRecordStatus.PENDING.value:
            summary["pending_count"] += 1
        elif status_val == PenaltyRecordStatus.APPROVED.value:
            summary["approved_count"] += 1
            summary["total_owed"] += fee
        elif status_val == PenaltyRecordStatus.REVERSAL_PENDING.value:
            summary["reversal_pending_count"] += 1
            summary["total_owed"] += fee
        elif status_val == PenaltyRecordStatus.PAID.value:
            summary["paid_count"] += 1
            summary["total_owed"] += fee
        elif status_val == PenaltyRecordStatus.REVERSED.value:
            summary["reversed_count"] += 1

        # Detect if this penalty was charged against a reconciliation
        # declaration — the compliance sweep should reverse those, but
        # showing the flag helps the member understand pending reversals.
        ptype_name = (ptype.name if ptype else "") or ""
        k_lower = ptype_name.strip().lower()
        is_cycle_defined = (
            ("late" in k_lower and "declaration" in k_lower)
            or ("late" in k_lower and "deposit" in k_lower)
            or ("late" in k_lower and "loan" in k_lower and "application" in k_lower)
        )
        is_reconciliation_penalty = False
        if is_cycle_defined:
            eff = _extract_effective_month_from_notes(p.notes or "")
            if not eff and p.date_issued:
                eff = _date(p.date_issued.year, p.date_issued.month, 1)
            if eff and is_reconciliation_declaration_for_member_month(
                db, member_profile.id, eff.year, eff.month,
            ):
                is_reconciliation_penalty = True

        rows.append({
            "id": str(p.id),
            "penalty_type_name": ptype_name or "Unknown",
            "penalty_type_description": ptype.description if ptype else None,
            "fee_amount": fee,
            "status": status_val,
            "date_issued": p.date_issued.isoformat() if p.date_issued else None,
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
            "notes": p.notes,
            "reversal_reason": p.reversal_reason,
            "reversal_requested_at": p.reversal_requested_at.isoformat() if p.reversal_requested_at else None,
            "reversed_at": p.reversed_at.isoformat() if p.reversed_at else None,
            "is_reconciliation_penalty": is_reconciliation_penalty,
        })

    # Ghost declared penalties — same diagnostic the compliance dashboard
    # shows, scoped to the caller. Any month where declared_penalties on
    # the member's Declaration exceeds the sum of matching live
    # PenaltyRecord fees for that effective month.
    from app.models.transaction import Declaration, DeclarationStatus
    from datetime import date as _date

    ghosts: list[dict] = []
    live_pen_statuses = {
        PenaltyRecordStatus.APPROVED.value,
        PenaltyRecordStatus.PAID.value,
        PenaltyRecordStatus.REVERSAL_PENDING.value,
        PenaltyRecordStatus.PENDING.value,
    }
    live_by_month: dict = {}
    for p in penalties:
        status_val = p.status.value if isinstance(p.status, PenaltyRecordStatus) else p.status
        if status_val not in live_pen_statuses:
            continue
        eff = _extract_effective_month_from_notes(p.notes or "") if p.notes else None
        if not eff and p.date_issued:
            eff = _date(p.date_issued.year, p.date_issued.month, 1)
        if not eff:
            continue
        key = (eff.year, eff.month)
        fee = float(p.penalty_type.fee_amount) if p.penalty_type and p.penalty_type.fee_amount else 0.0
        live_by_month[key] = live_by_month.get(key, 0.0) + fee

    decls = (
        db.query(Declaration)
        .filter(
            Declaration.member_id == member_profile.id,
            Declaration.status == DeclarationStatus.APPROVED,
            Declaration.declared_penalties > 0,
        )
        .order_by(Declaration.effective_month.asc())
        .all()
    )
    # Greedy consume with 1-month carry-back: for each declaration, first
    # consume live records with the same effective month, then any unclaimed
    # leftovers from the previous month (handles fees issued near month-end
    # that the member reasonably declares next month, e.g. Emergency Loan
    # fees auto-issued Jun 29 and declared in the July declaration).
    remaining_by_month = dict(live_by_month)
    for d in decls:
        declared = float(d.declared_penalties or 0)
        if declared <= 0:
            continue
        key_curr = (d.effective_month.year, d.effective_month.month)
        if d.effective_month.month == 1:
            key_prev = (d.effective_month.year - 1, 12)
        else:
            key_prev = (d.effective_month.year, d.effective_month.month - 1)
        avail_curr = remaining_by_month.get(key_curr, 0.0)
        avail_prev = remaining_by_month.get(key_prev, 0.0)
        take_curr = min(declared, avail_curr)
        take_prev = min(declared - take_curr, avail_prev)
        remaining_by_month[key_curr] = avail_curr - take_curr
        remaining_by_month[key_prev] = avail_prev - take_prev
        matched = take_curr + take_prev
        gap = round(declared - matched, 2)
        if gap > 0.01:
            ghosts.append({
                "effective_month": d.effective_month.isoformat(),
                "declared": declared,
                "matched_records": round(matched, 2),
                "ghost_amount": gap,
            })

    return {
        "member_id": str(member_profile.id),
        "summary": summary,
        "penalties": rows,
        "ghost_declared_penalties": ghosts,
    }


@router.get("/declarations/applicable-penalties")
def get_applicable_penalties(
    cycle_id: str,
    effective_month: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all applicable penalties for a declaration.
    
    Only includes penalties with APPROVED status. PENDING penalties are not included
    until approved by treasurer. PAID penalties are excluded as they have already been paid.
    Cycle-defined penalties (Late Declaration, Late Deposits, Late Loan Application) are
    automatically created with APPROVED status and will appear here.
    
    This function also checks if the declaration is late and creates the penalty record
    if it doesn't exist yet, so it can be included in the declaration form.
    """
    from datetime import date
    from app.models.transaction import PenaltyRecord, PenaltyRecordStatus, PenaltyType
    from app.models.cycle import CyclePhase, PhaseType
    from sqlalchemy import extract, or_, and_
    from uuid import UUID
    from app.services.transaction import get_system_user_id
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return {"total_amount": 0.0, "penalties": []}
    
    try:
        cycle_uuid = UUID(cycle_id)
        effective_date = date.fromisoformat(effective_month)
    except (ValueError, TypeError):
        return {"total_amount": 0.0, "penalties": []}
    
    # Check if declaration is late and create penalty record if needed
    declaration_phase = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == cycle_uuid,
        CyclePhase.phase_type == PhaseType.DECLARATION
    ).first()
    
    if declaration_phase:
        auto_apply = getattr(declaration_phase, 'auto_apply_penalty', False)
        monthly_end_day = getattr(declaration_phase, 'monthly_end_day', None)
        penalty_type_id = getattr(declaration_phase, 'penalty_type_id', None)

        if auto_apply and monthly_end_day and penalty_type_id:
            today = date.today()
            is_late = False

            # Check if a declaration already exists for this month.
            # If yes, the member declared on time and is just editing —
            # do NOT apply a late declaration penalty.
            existing_declaration = db.query(Declaration).filter(
                Declaration.member_id == member_profile.id,
                extract('year', Declaration.effective_month) == effective_date.year,
                extract('month', Declaration.effective_month) == effective_date.month,
            ).first()

            if existing_declaration:
                # Skip if this declaration was created via treasurer
                # reconciliation — the treasurer entered it retroactively,
                # not a live member submission missing the window.
                from app.services.transaction import is_reconciliation_declaration
                if is_reconciliation_declaration(db, existing_declaration.id):
                    is_late = False
                # Member already has a declaration — they declared on time.
                # Check if the ORIGINAL declaration was made late
                # (only apply penalty if the declaration was first created after the deadline).
                elif existing_declaration.created_at:
                    created_day = existing_declaration.created_at.day
                    is_late = created_day > monthly_end_day
                else:
                    is_late = False
            else:
                # No declaration yet — check if today is past the deadline
                if today.year == effective_date.year and today.month == effective_date.month:
                    if today.day > monthly_end_day:
                        is_late = True
                elif today.year > effective_date.year or (today.year == effective_date.year and today.month > effective_date.month):
                    is_late = True

            if is_late:
                # Check if penalty record already exists for this declaration
                # More comprehensive duplicate check: check by member, penalty_type, and effective month
                # This prevents duplicates even if called multiple times
                from sqlalchemy import extract, or_, and_
                existing_penalty = db.query(PenaltyRecord).filter(
                    PenaltyRecord.member_id == member_profile.id,
                    PenaltyRecord.penalty_type_id == penalty_type_id,
                    or_(
                        # Check by date_issued year/month (if created in same month)
                        and_(
                            extract('year', PenaltyRecord.date_issued) == effective_date.year,
                            extract('month', PenaltyRecord.date_issued) == effective_date.month
                        ),
                        # Check by notes containing the effective month (case-insensitive)
                        PenaltyRecord.notes.ilike(f"%{effective_date.strftime('%B %Y')}%"),
                        PenaltyRecord.notes.ilike(f"%{effective_date.strftime('%b %Y')}%")  # Also check abbreviated month
                    )
                ).first()
                
                if not existing_penalty:
                    # Get penalty type
                    penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                    if penalty_type:
                        # Get system user for system-generated penalties
                        system_user_id = get_system_user_id(db)
                        if system_user_id:
                            # Rich audit narration — same shape as the
                            # write-path in transaction.py::create_declaration
                            # so a compliance officer reading either source
                            # sees consistent language.
                            from app.services.transaction import build_late_penalty_narration
                            try:
                                import calendar as _cal
                                _, _last_day = _cal.monthrange(effective_date.year, effective_date.month)
                                _decl_end_date = _date(
                                    effective_date.year,
                                    effective_date.month,
                                    min(monthly_end_day, _last_day),
                                )
                            except Exception:
                                _decl_end_date = None
                            _decl_offending_at = (
                                getattr(existing_declaration, "created_at", None)
                                if existing_declaration else None
                            ) or datetime.utcnow()
                            _narration = build_late_penalty_narration(
                                kind="Late Declaration",
                                effective_month=effective_date,
                                offending_at=_decl_offending_at,
                                period_end=_decl_end_date,
                                monthly_end_day=monthly_end_day,
                            )
                            # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                            penalty_obj = PenaltyRecord(
                                id=uuid.uuid4(),
                                member_id=member_profile.id,
                                penalty_type_id=penalty_type_id,
                                status=PenaltyRecordStatus.APPROVED,
                                created_by=system_user_id,
                                notes=_narration,
                                date_issued=datetime.utcnow(),
                            )
                            db.add(penalty_obj)
                            db.commit()
    
    # Get all cycle phases to check auto_apply_penalty flags
    all_phases = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == cycle_uuid
    ).all()
    
    # Build a map of penalty_type_id -> auto_apply_penalty flag
    # This tells us which cycle-defined penalties should be included
    penalty_type_auto_apply_map = {}
    for phase in all_phases:
        if phase.penalty_type_id:
            penalty_type_auto_apply_map[phase.penalty_type_id] = getattr(phase, 'auto_apply_penalty', False)
    
    penalties_list = []
    total_amount = Decimal("0.00")
    
    # Get only APPROVED penalty records (not PENDING, not PAID)
    # PENDING penalties need treasurer approval first
    # PAID penalties have already been paid and should not be included
    approved_penalty_records = db.query(PenaltyRecord).filter(
        PenaltyRecord.member_id == member_profile.id,
        PenaltyRecord.status == PenaltyRecordStatus.APPROVED
    ).order_by(PenaltyRecord.date_issued.desc()).all()
    
    # Track seen penalties to prevent duplicates
    # For cycle-defined penalties, use (penalty_type_id, effective_month) as key
    # For other penalties, use penalty_id as key
    seen_penalty_keys = set()
    
    for penalty in approved_penalty_records:
        penalty_type = penalty.penalty_type
        if not penalty_type:
            continue
            
        # Check if this is a cycle-defined penalty type
        from app.services.transaction import is_cycle_defined_penalty_type
        is_cycle_defined = is_cycle_defined_penalty_type(penalty_type.name)
        
        # If it's a cycle-defined penalty, check if auto_apply_penalty is enabled
        if is_cycle_defined:
            auto_apply = penalty_type_auto_apply_map.get(penalty.penalty_type_id, False)
            # If auto_apply_penalty is False, exclude this penalty from applicable penalties
            if not auto_apply:
                continue
            
            # For cycle-defined penalties, create a deduplication key based on penalty_type_id and effective month
            # Use the effective_month from the function parameter for accurate matching
            dedup_key = f"{penalty.penalty_type_id}_{effective_date.year}_{effective_date.month}"
            
            # Also check if notes contain the effective month (for additional safety)
            notes_match = False
            if penalty.notes:
                month_year_str = effective_date.strftime('%B %Y')  # e.g., "January 2026"
                month_year_short = effective_date.strftime('%b %Y')  # e.g., "Jan 2026"
                if month_year_str in penalty.notes or month_year_short in penalty.notes:
                    notes_match = True
            
            # Check if date_issued is in the same month/year as effective_date
            date_match = False
            if penalty.date_issued:
                date_match = (penalty.date_issued.year == effective_date.year and 
                             penalty.date_issued.month == effective_date.month)
            
            # Only include if notes or date matches the effective month
            # This ensures we only deduplicate penalties for the same effective month
            if notes_match or date_match:
                # If we've seen this penalty type for this effective month, skip duplicate
                if dedup_key in seen_penalty_keys:
                    continue
                seen_penalty_keys.add(dedup_key)
            else:
                # If it doesn't match the effective month, use penalty_id to avoid false positives
                penalty_key = str(penalty.id)
                if penalty_key in seen_penalty_keys:
                    continue
                seen_penalty_keys.add(penalty_key)
        else:
            # For non-cycle-defined penalties, use penalty_id as key
            penalty_key = str(penalty.id)
            if penalty_key in seen_penalty_keys:
                continue
            seen_penalty_keys.add(penalty_key)
        
        fee_amount = penalty_type.fee_amount if penalty_type else Decimal("0.00")
        total_amount += fee_amount
        
        penalties_list.append({
            "id": str(penalty.id),
            "penalty_type_name": penalty_type.name if penalty_type else "Unknown",
            "fee_amount": float(fee_amount),
            "date_issued": penalty.date_issued.isoformat() if penalty.date_issued else None,
            "notes": penalty.notes,
            "source": "penalty_record"
        })
    
    return {
        "total_amount": float(total_amount),
        "penalties": penalties_list
    }


@router.get("/declarations/late-penalty")
def get_late_declaration_penalty(
    cycle_id: str,
    effective_month: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get penalty amount for late declaration based on cycle phase configuration.
    
    Checks if the declaration is being made after the declaration period end day,
    and if auto_apply_penalty is enabled, returns the penalty amount from the cycle phase.
    """
    from datetime import date
    from app.models.cycle import Cycle, CyclePhase, PhaseType
    from uuid import UUID
    
    try:
        cycle_uuid = UUID(cycle_id)
        effective_date = date.fromisoformat(effective_month)
    except (ValueError, TypeError):
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Invalid cycle_id or effective_month"}
    
    # Get the cycle
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Cycle not found"}
    
    # Get the declaration phase for this cycle
    declaration_phase = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == cycle_uuid,
        CyclePhase.phase_type == PhaseType.DECLARATION
    ).first()
    
    if not declaration_phase:
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Declaration phase not configured"}
    
    # Check if auto_apply_penalty is enabled
    if not getattr(declaration_phase, 'auto_apply_penalty', False):
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Auto-apply penalty not enabled"}
    
    # Check if monthly_end_day is set
    monthly_end_day = getattr(declaration_phase, 'monthly_end_day', None)
    if not monthly_end_day:
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Declaration period end day not configured"}
    
    # Check if today's date is after the end day of the effective month
    today = date.today()
    is_late = False
    
    # If declaration is for current month and today is after the end day
    if today.year == effective_date.year and today.month == effective_date.month:
        if today.day > monthly_end_day:
            is_late = True
    # Also check if declaration is for a past month (always late)
    elif today.year > effective_date.year or (today.year == effective_date.year and today.month > effective_date.month):
        is_late = True
    
    if not is_late:
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Declaration is not late"}
    
    # Get penalty type and amount
    penalty_type_id = getattr(declaration_phase, 'penalty_type_id', None)
    if not penalty_type_id:
        # Fallback to deprecated penalty_amount if penalty_type_id not set
        penalty_amount = getattr(declaration_phase, 'penalty_amount', None)
        if penalty_amount:
            return {
                "penalty_amount": float(penalty_amount),
                "penalty_type_name": "Late Declaration Penalty",
                "reason": f"Declaration made after day {monthly_end_day} of the month"
            }
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "No penalty type configured"}
    
    # Get penalty type details
    from app.models.transaction import PenaltyType
    penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
    if not penalty_type:
        return {"penalty_amount": 0.0, "penalty_type_name": None, "reason": "Penalty type not found"}
    
    return {
        "penalty_amount": float(penalty_type.fee_amount),
        "penalty_type_name": penalty_type.name,
        "penalty_type_id": str(penalty_type.id),
        "reason": f"Declaration made after day {monthly_end_day} of the month",
        "monthly_end_day": monthly_end_day
    }


@router.get("/declarations")
def get_my_declarations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get my declarations. All authenticated users can view their declarations."""
    from datetime import date
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return []
    
    declarations = db.query(Declaration).filter(
        Declaration.member_id == member_profile.id
    ).order_by(Declaration.effective_month.desc(), Declaration.created_at.desc()).all()
    
    today = date.today()
    
    result = []
    for d in declarations:
        # Check for rejected deposit proof
        rejected_proof = db.query(DepositProof).filter(
            DepositProof.declaration_id == d.id,
            DepositProof.status == DepositProofStatus.REJECTED.value
        ).first()
        
        rejected_deposit_proof = None
        if rejected_proof:
            rejected_deposit_proof = {
                "id": str(rejected_proof.id),
                "amount": float(rejected_proof.amount),
                "reference": rejected_proof.reference,
                "treasurer_comment": rejected_proof.treasurer_comment,
                "member_response": rejected_proof.member_response,
                "upload_path": rejected_proof.upload_path,
                "rejected_at": rejected_proof.rejected_at.isoformat() if rejected_proof.rejected_at else None
            }

        # Provenance flags for the at-a-glance UI legend:
        #   has_real_proof       — at least one non-superseded DepositProof exists
        #                          with a real file (upload_path is not the
        #                          "reconciliation" marker and not empty)
        #   created_via_reconciliation — any DepositProof on this declaration is
        #                          a reconciliation marker (legacy reconciliation
        #                          flow created these)
        #   approved_via_reconciliation — declaration is APPROVED AND its
        #                          approval was based on a reconciliation marker
        #                          (no real proof file ever existed)
        all_proofs = db.query(DepositProof).filter(
            DepositProof.declaration_id == d.id,
        ).all()
        live_proofs = [p for p in all_proofs if p.status != "superseded"]
        has_real_proof = any(
            (p.upload_path and p.upload_path != "reconciliation")
            for p in live_proofs
        )
        created_via_reconciliation = any(
            p.upload_path == "reconciliation" for p in all_proofs
        )
        approved_via_reconciliation = bool(
            d.status == DeclarationStatus.APPROVED
            and not has_real_proof
            and any(
                p.upload_path == "reconciliation"
                and p.status == DepositProofStatus.APPROVED.value
                for p in all_proofs
            )
        )

        # Compute live posted amounts per category for this declaration's month
        # and flag when they diverge from the declared figures (i.e. treasurer
        # used Posted Transactions to reverse, split or move a line).
        from app.services.accounting import compute_posted_breakdown as _posted_bd
        posted_items = _posted_bd(db, member_profile.id, d.effective_month.year, d.effective_month.month)
        declared_items = {
            "savings": float(d.declared_savings_amount or 0),
            "social_fund": float(d.declared_social_fund or 0),
            "admin_fund": float(d.declared_admin_fund or 0),
            "penalty": float(d.declared_penalties or 0),
        }
        # Only flag when this declaration was actually posted (otherwise pending
        # declarations would show as "discrepant" because posted is 0).
        has_reconciliation_discrepancy = (
            d.status == DeclarationStatus.APPROVED
            and any(abs(posted_items[k] - declared_items[k]) > 0.01 for k in declared_items)
        )

        result.append({
            "id": str(d.id),
            "cycle_id": str(d.cycle_id),
            "effective_month": d.effective_month.isoformat(),
            "declared_savings_amount": float(d.declared_savings_amount) if d.declared_savings_amount else None,
            "declared_social_fund": float(d.declared_social_fund) if d.declared_social_fund else None,
            "declared_admin_fund": float(d.declared_admin_fund) if d.declared_admin_fund else None,
            "declared_penalties": float(d.declared_penalties) if d.declared_penalties else None,
            "declared_interest_on_loan": float(d.declared_interest_on_loan) if d.declared_interest_on_loan else None,
            "declared_loan_repayment": float(d.declared_loan_repayment) if d.declared_loan_repayment else None,
            "status": d.status.value,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            "can_edit": (
                _can_edit_declaration(d.effective_month) and d.status == DeclarationStatus.PENDING
            ) or (
                # Allow editing if there's a rejected deposit proof for this declaration
                rejected_proof is not None
            ),
            "rejected_deposit_proof": rejected_deposit_proof,
            "has_real_proof": has_real_proof,
            "created_via_reconciliation": created_via_reconciliation,
            "approved_via_reconciliation": approved_via_reconciliation,
            "posted_items": posted_items,
            "has_reconciliation_discrepancy": has_reconciliation_discrepancy,
        })
    
    return result


@router.get("/declarations/current-month")
def get_current_month_declaration(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get declaration for the current month if it exists."""
    from sqlalchemy import and_, extract
    from datetime import date
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return None
    
    today = date.today()
    
    # Get active cycle
    from app.models.cycle import Cycle, CycleStatus
    active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
    if not active_cycle:
        return None
    
    # Check for declaration in current month
    declaration = db.query(Declaration).filter(
        and_(
            Declaration.member_id == member_profile.id,
            Declaration.cycle_id == active_cycle.id,
            extract('year', Declaration.effective_month) == today.year,
            extract('month', Declaration.effective_month) == today.month
        )
    ).first()
    
    if not declaration:
        return None
    
    # Check for rejected deposit proof
    rejected_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration.id,
        DepositProof.status == DepositProofStatus.REJECTED.value
    ).first()
    
    rejected_deposit_proof = None
    if rejected_proof:
        rejected_deposit_proof = {
            "id": str(rejected_proof.id),
            "amount": float(rejected_proof.amount),
            "reference": rejected_proof.reference,
            "treasurer_comment": rejected_proof.treasurer_comment,
            "member_response": rejected_proof.member_response,
            "upload_path": rejected_proof.upload_path,
            "rejected_at": rejected_proof.rejected_at.isoformat() if rejected_proof.rejected_at else None
        }
    
    return {
        "id": str(declaration.id),
        "cycle_id": str(declaration.cycle_id),
        "effective_month": declaration.effective_month.isoformat(),
        "declared_savings_amount": float(declaration.declared_savings_amount) if declaration.declared_savings_amount else None,
        "declared_social_fund": float(declaration.declared_social_fund) if declaration.declared_social_fund else None,
        "declared_admin_fund": float(declaration.declared_admin_fund) if declaration.declared_admin_fund else None,
        "declared_penalties": float(declaration.declared_penalties) if declaration.declared_penalties else None,
        "declared_interest_on_loan": float(declaration.declared_interest_on_loan) if declaration.declared_interest_on_loan else None,
        "declared_loan_repayment": float(declaration.declared_loan_repayment) if declaration.declared_loan_repayment else None,
        "status": declaration.status.value,
        "created_at": declaration.created_at.isoformat() if declaration.created_at else None,
        "updated_at": declaration.updated_at.isoformat() if declaration.updated_at else None,
        "can_edit": _can_edit_declaration(declaration.effective_month) or (rejected_proof is not None),
        "rejected_deposit_proof": rejected_deposit_proof
    }


def _can_edit_declaration(effective_month: date) -> bool:
    """Check if a declaration can still be edited.

    Declarations can only be created/edited between the 15th of the effective
    month and the 5th of the following month.
    """
    from datetime import date
    today = date.today()

    # Determine the valid editing window for this effective month
    window_open = date(effective_month.year, effective_month.month, 15)
    if effective_month.month == 12:
        window_close = date(effective_month.year + 1, 1, 5)
    else:
        window_close = date(effective_month.year, effective_month.month + 1, 5)

    return window_open <= today <= window_close


# ---------------------------------------------------------------------------
# Bank Statement endpoints (member – read-only)
# ---------------------------------------------------------------------------

@router.get("/bank-statements")
def list_member_bank_statements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List bank statements for the active cycle (read-only for any authenticated user)."""
    from pathlib import Path
    from app.models.cycle import Cycle, CycleStatus

    cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
    if not cycle:
        return {"statements": []}

    stmts = (
        db.query(BankStatement)
        .filter(BankStatement.cycle_id == cycle.id)
        .order_by(BankStatement.statement_month.desc())
        .all()
    )

    return {
        "statements": [
            {
                "id": str(s.id),
                "cycle_id": str(s.cycle_id),
                "statement_month": s.statement_month.isoformat(),
                "description": s.description,
                "filename": Path(s.upload_path).name,
                "uploaded_at": s.uploaded_at.isoformat() if s.uploaded_at else None
            }
            for s in stmts
        ]
    }


@router.get("/bank-statements/file/{filename:path}")
def get_member_bank_statement_file(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Serve a bank statement file to any authenticated user."""
    from pathlib import Path
    from urllib.parse import unquote
    from fastapi.responses import FileResponse
    from app.core.config import BANK_STATEMENTS_DIR

    filename = unquote(filename)
    safe_filename = Path(filename).name
    file_path = BANK_STATEMENTS_DIR / safe_filename

    if not file_path.exists() or not str(file_path.resolve()).startswith(str(BANK_STATEMENTS_DIR.resolve())):
        raise HTTPException(status_code=404, detail="File not found")

    ext = Path(safe_filename).suffix.lower()
    media_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(path=str(file_path), filename=safe_filename, media_type=media_type)


@router.put("/declarations/{declaration_id}")
def update_declaration_endpoint(
    declaration_id: str,
    declaration_data: DeclarationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a declaration. Allowed for current month declarations (one per month rule still applies)."""
    from uuid import UUID
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(
            status_code=403, 
            detail="Member profile not found"
        )
    
    try:
        declaration_uuid = UUID(declaration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid declaration ID format")
    
    # Verify the declaration belongs to the current user
    declaration = db.query(Declaration).filter(Declaration.id == declaration_uuid).first()
    if not declaration:
        raise HTTPException(status_code=404, detail="Declaration not found")
    
    if declaration.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only edit your own declarations")
    
    # Editability is status-based, not date-based: a declaration can be edited
    # iff it is pending or rejected (or has a rejected proof attached). Approved
    # declarations are immutable — they're posted to the ledger, and to change
    # them the treasurer must use Reports → Reject Declaration first, which
    # moves the status back to pending.
    rejected_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration_uuid,
        DepositProof.status == DepositProofStatus.REJECTED.value
    ).first()
    editable = (
        declaration.status in (DeclarationStatus.PENDING, DeclarationStatus.REJECTED)
        or rejected_proof is not None
    )
    if not editable:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This declaration is {declaration.status.value} and cannot be edited. "
                "Ask the treasurer to reject it first (Reports → Reject Declaration) "
                "if changes are needed."
            ),
        )

    try:
        # Use `is not None` (NOT truthiness) so a legitimate 0 reaches the
        # service layer. Zeroing out a field is a valid edit — "I declared
        # K200 interest but actually owe none this month" must land as
        # Decimal("0"), not None (which the service treats as "skip").
        updated_declaration = update_declaration(
            db=db,
            declaration_id=declaration_uuid,
            member_id=member_profile.id,
            cycle_id=UUID(declaration_data.cycle_id),
            effective_month=declaration_data.effective_month,
            declared_savings_amount=Decimal(str(declaration_data.declared_savings_amount)) if declaration_data.declared_savings_amount is not None else None,
            declared_social_fund=Decimal(str(declaration_data.declared_social_fund)) if declaration_data.declared_social_fund is not None else None,
            declared_admin_fund=Decimal(str(declaration_data.declared_admin_fund)) if declaration_data.declared_admin_fund is not None else None,
            declared_penalties=Decimal(str(declaration_data.declared_penalties)) if declaration_data.declared_penalties is not None else None,
            declared_interest_on_loan=Decimal(str(declaration_data.declared_interest_on_loan)) if declaration_data.declared_interest_on_loan is not None else None,
            declared_loan_repayment=Decimal(str(declaration_data.declared_loan_repayment)) if declaration_data.declared_loan_repayment is not None else None,
            allow_rejected_edit=editable,
        )
        return {"message": "Declaration updated successfully", "declaration_id": str(updated_declaration.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/loans/eligibility/{cycle_id}")
def get_loan_eligibility(
    cycle_id: str,
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db)
):
    """Get loan eligibility information for the current user (max loan amount, available terms, interest rates).
    Available to all authenticated users except admin."""
    from app.models.cycle import Cycle, CycleStatus
    from app.models.policy import MemberCreditRating, CreditRatingTier, BorrowingLimitPolicy, CreditRatingInterestRange
    from app.services.accounting import get_member_savings_balance
    
    # Get or create member profile if it doesn't exist
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        # Create member profile automatically if it doesn't exist
        from app.models.member import MemberProfile
        member_profile = MemberProfile(
            user_id=current_user.id,
            status=MemberStatus.ACTIVE
        )
        db.add(member_profile)
        db.commit()
        db.refresh(member_profile)
    
    if member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Member account is not active")
    
    try:
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cycle ID format")
    
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    
    # Get member's credit rating for this cycle
    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == cycle_uuid
    ).first()
    
    if not credit_rating:
        return {
            "has_credit_rating": False,
            "message": "No credit rating assigned. Please contact the administrator."
        }
    
    # Get tier details
    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == credit_rating.tier_id).first()
    if not tier:
        return {
            "has_credit_rating": False,
            "message": "Credit rating tier not found."
        }
    
    # Get borrowing limit (multiplier)
    borrowing_limit = db.query(BorrowingLimitPolicy).filter(
        BorrowingLimitPolicy.tier_id == tier.id,
        BorrowingLimitPolicy.effective_from <= cycle.end_date
    ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
    
    if not borrowing_limit:
        return {
            "has_credit_rating": True,
            "message": "Borrowing limit not configured for this tier."
        }
    
    # Get member's savings balance
    savings_balance = get_member_savings_balance(db, member_profile.id)
    
    # Calculate max loan amount
    max_loan_amount = savings_balance * borrowing_limit.multiplier
    
    # Get available interest rates for this tier
    interest_ranges = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == tier.id,
        CreditRatingInterestRange.cycle_id == cycle_uuid
    ).all()
    
    # Format available terms
    available_terms = []
    for ir in interest_ranges:
        if ir.term_months is None:
            # This applies to all terms
            available_terms.append({
                "term_months": None,
                "term_label": "All Terms",
                "interest_rate": float(ir.effective_rate_percent)
            })
        else:
            available_terms.append({
                "term_months": ir.term_months,
                "term_label": f"{ir.term_months} Month{'s' if ir.term_months != '1' else ''}",
                "interest_rate": float(ir.effective_rate_percent)
            })
    
    # Sort by term months ascending (None/"All Terms" entries go first)
    available_terms.sort(key=lambda t: int(t["term_months"]) if t["term_months"] else 0)

    return {
        "has_credit_rating": True,
        "tier_name": tier.tier_name,
        "tier_order": tier.tier_order,
        "savings_balance": float(savings_balance),
        "multiplier": float(borrowing_limit.multiplier),
        "max_loan_amount": float(max_loan_amount),
        "available_terms": available_terms
    }


@router.post("/loans/apply")
def apply_for_loan(
    loan_data: LoanApplicationCreate,
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db)
):
    """Apply for a loan. Validates loan amount against maximum allowed based on credit rating.
    Available to all authenticated users except admin.
    Prevents multiple pending loan applications."""
    from app.models.cycle import Cycle
    from app.models.policy import MemberCreditRating, BorrowingLimitPolicy, CreditRatingInterestRange
    from app.services.accounting import get_member_savings_balance
    from app.models.transaction import LoanApplicationStatus, Loan, LoanStatus
    
    # Get or create member profile if it doesn't exist
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        # Create member profile automatically if it doesn't exist
        from app.models.member import MemberProfile
        member_profile = MemberProfile(
            user_id=current_user.id,
            status=MemberStatus.ACTIVE
        )
        db.add(member_profile)
        db.commit()
        db.refresh(member_profile)
    
    if member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Member account is not active")
    
    # Check for pending loan applications
    pending_application = db.query(LoanApplication).filter(
        LoanApplication.member_id == member_profile.id,
        LoanApplication.status == LoanApplicationStatus.PENDING
    ).first()
    
    if pending_application:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have a pending loan application. Please wait for it to be processed or withdraw it before applying for a new loan."
        )
    
    # Check for active loans that haven't been fully paid.
    # If the member still owes on an active loan we normally refuse, but
    # allow the flexibility: if the member has already SUBMITTED a
    # declaration (PENDING or PROOF status) whose declared_loan_repayment
    # + declared_interest_on_loan covers the full outstanding balance, the
    # payoff is committed and we let the new application through. The
    # treasurer will still see a "pending payoff" badge on the application
    # so they only disburse the new loan after the payoff deposit lands.
    from app.models.transaction import DeclarationStatus as _DeclStatus
    active_loans = db.query(Loan).filter(
        Loan.member_id == member_profile.id,
        Loan.loan_status.in_([LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN])
    ).all()

    total_outstanding = Decimal("0.00")
    for loan in active_loans:
        total_p_repaid = sum(
            Decimal(str(rep.principal_amount or 0)) for rep in loan.repayments
        )
        total_i_repaid = sum(
            Decimal(str(rep.interest_amount or 0)) for rep in loan.repayments
        )
        outstanding_p = Decimal(str(loan.loan_amount or 0)) - total_p_repaid
        expected_interest = (
            Decimal(str(loan.loan_amount or 0))
            * Decimal(str(loan.percentage_interest or 0))
            / Decimal("100")
        )
        outstanding_i = expected_interest - total_i_repaid
        # A loan is "fully paid" when both principal AND interest are settled.
        # We only count it as outstanding when either side has more than
        # rounding-noise left.
        if outstanding_p > Decimal("0.01"):
            total_outstanding += outstanding_p
        if outstanding_i > Decimal("0.01"):
            total_outstanding += outstanding_i

    if total_outstanding > Decimal("0.01"):
        # Sum every pending / proof declaration's committed payoff. Approved
        # declarations aren't included — once approved, their repayment is
        # already posted and reflected in outstanding.
        pending_payoff = Decimal("0.00")
        pending_decls = db.query(Declaration).filter(
            Declaration.member_id == member_profile.id,
            Declaration.status.in_([_DeclStatus.PENDING, _DeclStatus.PROOF]),
        ).all()
        for d in pending_decls:
            pending_payoff += Decimal(str(d.declared_loan_repayment or 0))
            pending_payoff += Decimal(str(d.declared_interest_on_loan or 0))

        if pending_payoff + Decimal("0.01") < total_outstanding:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"You have an active loan with outstanding balance of K{total_outstanding:,.2f}. "
                    f"You have declared K{pending_payoff:,.2f} in pending declarations towards "
                    "payoff — submit a declaration covering the full outstanding balance before "
                    "applying for a new loan, or wait for the current loan to close."
                )
            )
        # else: falls through — the pending declaration covers payoff and the
        # application is allowed. The treasurer will see the pending-payoff
        # badge on the application card.
    
    try:
        cycle_uuid = UUID(loan_data.cycle_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cycle ID format")
    
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    
    # Get member's credit rating
    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == cycle_uuid
    ).first()
    
    if not credit_rating:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No credit rating assigned. Please contact the administrator to assign a credit rating."
        )
    
    # Get borrowing limit
    borrowing_limit = db.query(BorrowingLimitPolicy).filter(
        BorrowingLimitPolicy.tier_id == credit_rating.tier_id
    ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
    
    if not borrowing_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Borrowing limit not configured for your credit rating tier."
        )
    
    # Get savings balance and calculate max loan amount
    savings_balance = get_member_savings_balance(db, member_profile.id)
    max_loan_amount = savings_balance * borrowing_limit.multiplier
    
    # Validate loan amount
    loan_amount = Decimal(str(loan_data.amount))
    if loan_amount > max_loan_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loan amount (K{loan_amount:,.2f}) exceeds maximum allowed (K{max_loan_amount:,.2f}) based on your savings balance (K{savings_balance:,.2f}) and credit rating multiplier ({borrowing_limit.multiplier}x)."
        )
    
    # Validate term is available for this tier
    interest_range = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == credit_rating.tier_id,
        CreditRatingInterestRange.cycle_id == cycle_uuid,
        (CreditRatingInterestRange.term_months == loan_data.term_months) | (CreditRatingInterestRange.term_months.is_(None))
    ).first()
    
    if not interest_range:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loan term of {loan_data.term_months} month(s) is not available for your credit rating tier."
        )
    
    loan_application_kwargs = dict(
        member_id=member_profile.id,
        cycle_id=cycle_uuid,
        amount=loan_amount,
        term_months=loan_data.term_months,
        status=LoanApplicationStatus.PENDING,
    )
    if loan_data.borrowing_date:
        try:
            borrow_dt = date.fromisoformat(loan_data.borrowing_date)
            loan_application_kwargs["application_date"] = datetime.combine(borrow_dt, datetime.min.time())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid borrowing_date format. Use YYYY-MM-DD.",
            )
    loan_application = LoanApplication(**loan_application_kwargs)
    db.add(loan_application)
    db.flush()  # Flush to get loan_application.id
    
    # Check if loan application is late and create automatic penalty record
    from app.models.cycle import CyclePhase, PhaseType
    from datetime import date as date_type
    
    loan_application_phase = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == cycle_uuid,
        CyclePhase.phase_type == PhaseType.LOAN_APPLICATION
    ).first()
    
    if loan_application_phase:
        auto_apply = getattr(loan_application_phase, 'auto_apply_penalty', False)
        monthly_end_day = getattr(loan_application_phase, 'monthly_end_day', None)
        penalty_type_id = getattr(loan_application_phase, 'penalty_type_id', None)
        
        if auto_apply and monthly_end_day and penalty_type_id:
            today = date_type.today()
            is_late = False
            
            # Check if loan application is late (after monthly_end_day for the current month)
            if today.day > monthly_end_day:
                is_late = True

            # Skip if this member has a reconciliation-flagged declaration
            # for the same month — this loan application likely rides on
            # the treasurer's retrospective bookkeeping rather than a
            # missed live deadline.
            if is_late:
                from app.services.transaction import is_reconciliation_declaration_for_member_month
                if is_reconciliation_declaration_for_member_month(
                    db, member_profile.id, today.year, today.month
                ):
                    is_late = False

            if is_late:
                # Get penalty type
                from app.models.transaction import PenaltyType, PenaltyRecord, PenaltyRecordStatus
                penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                if penalty_type:
                    # Check if penalty record already exists for this loan application
                    existing_penalty = db.query(PenaltyRecord).filter(
                        PenaltyRecord.member_id == member_profile.id,
                        PenaltyRecord.penalty_type_id == penalty_type_id,
                        PenaltyRecord.notes.ilike(f"%Late Loan Application%{today.strftime('%B %Y')}%")
                    ).first()
                    
                    if not existing_penalty:
                        # Get system user for system-generated penalties
                        from app.services.transaction import get_system_user_id, build_late_penalty_narration
                        system_user_id = get_system_user_id(db)
                        if not system_user_id:
                            # If no admin exists, skip penalty creation (shouldn't happen in production)
                            import logging
                            logging.warning(f"No admin user found to create system penalty for member {member_profile.id}")
                        else:
                            # Rich audit narration — captures the exact
                            # timestamp of the loan application relative
                            # to the phase window.
                            _la_start_day = getattr(loan_application_phase, "monthly_start_day", None)
                            _la_effective_month = date_type(today.year, today.month, 1)
                            try:
                                import calendar as _cal
                                _, _last_day = _cal.monthrange(today.year, today.month)
                                _la_period_end = date_type(today.year, today.month, min(monthly_end_day, _last_day))
                            except Exception:
                                _la_period_end = None
                            _la_period_start = None
                            if _la_start_day:
                                try:
                                    _la_period_start = date_type(today.year, today.month, _la_start_day)
                                except Exception:
                                    _la_period_start = None
                            _la_offending_at = getattr(loan_application, "application_date", None) or datetime.utcnow()
                            _narration = build_late_penalty_narration(
                                kind="Late Loan Application",
                                effective_month=_la_effective_month,
                                offending_at=_la_offending_at,
                                period_start=_la_period_start,
                                period_end=_la_period_end,
                                monthly_start_day=_la_start_day,
                                monthly_end_day=monthly_end_day,
                            )
                            # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                            late_penalty = PenaltyRecord(
                                member_id=member_profile.id,
                                penalty_type_id=penalty_type_id,
                                status=PenaltyRecordStatus.APPROVED.value,  # Use .value to ensure lowercase string is sent
                                created_by=system_user_id,  # Use admin user for system-generated penalties
                                notes=_narration,
                            )
                            db.add(late_penalty)
                            db.flush()
    
    db.commit()
    db.refresh(loan_application)
    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "member",
        action="Loan application submitted",
        details=f"amount=K {loan_data.amount}"
    )
    return {
        "message": "Loan application submitted successfully",
        "application_id": str(loan_application.id),
        "max_loan_amount": float(max_loan_amount),
        "savings_balance": float(savings_balance),
        "multiplier": float(borrowing_limit.multiplier)
    }


@router.post("/loans/{application_id}/withdraw")
def withdraw_loan_application(
    application_id: str,
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db)
):
    """Withdraw a pending loan application by deleting it from the database.
    Only pending applications can be withdrawn. Available to all authenticated users except admin."""
    from app.models.transaction import LoanApplicationStatus
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member profile not found")
    
    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID format")
    
    application = db.query(LoanApplication).filter(
        LoanApplication.id == app_uuid,
        LoanApplication.member_id == member_profile.id
    ).first()
    
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan application not found")
    
    if application.status != LoanApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot withdraw application with status: {application.status.value}. Only pending applications can be withdrawn."
        )
    
    # Delete the application from database since it's not yet committed
    db.delete(application)
    db.commit()
    
    return {"message": "Loan application withdrawn and removed successfully"}


@router.put("/loans/{application_id}")
def update_loan_application(
    application_id: str,
    loan_data: LoanApplicationCreate,
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db)
):
    """Update a pending loan application (amount and notes). 
    Only pending applications can be edited. Available to all authenticated users except admin."""
    from app.models.transaction import LoanApplicationStatus
    from app.models.cycle import Cycle
    from app.models.policy import MemberCreditRating, BorrowingLimitPolicy, CreditRatingInterestRange
    from app.services.accounting import get_member_savings_balance
    from decimal import Decimal
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member profile not found")
    
    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID format")
    
    application = db.query(LoanApplication).filter(
        LoanApplication.id == app_uuid,
        LoanApplication.member_id == member_profile.id
    ).first()
    
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan application not found")
    
    if application.status != LoanApplicationStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit application with status: {application.status.value}. Only pending applications can be edited."
        )
    
    # Validate loan amount against credit rating and savings
    try:
        cycle_uuid = UUID(loan_data.cycle_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cycle ID format")
    
    cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
    if not cycle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cycle not found")
    
    # Get credit rating
    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == cycle_uuid
    ).first()
    
    if not credit_rating:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You do not have a credit rating for this cycle. Please contact the administrator."
        )
    
    # Get borrowing limit
    borrowing_limit = db.query(BorrowingLimitPolicy).filter(
        BorrowingLimitPolicy.tier_id == credit_rating.tier_id
    ).order_by(BorrowingLimitPolicy.effective_from.desc()).first()
    
    if not borrowing_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Borrowing limit not configured for your credit rating tier."
        )
    
    # Get savings balance and calculate max loan amount
    savings_balance = get_member_savings_balance(db, member_profile.id)
    max_loan_amount = savings_balance * borrowing_limit.multiplier
    
    # Validate loan amount
    loan_amount = Decimal(str(loan_data.amount))
    if loan_amount > max_loan_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loan amount (K{loan_amount:,.2f}) exceeds maximum allowed (K{max_loan_amount:,.2f}) based on your savings balance (K{savings_balance:,.2f}) and credit rating multiplier ({borrowing_limit.multiplier}x)."
        )
    
    # Validate loan term
    interest_range = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == credit_rating.tier_id,
        CreditRatingInterestRange.cycle_id == cycle_uuid,
        CreditRatingInterestRange.term_months == loan_data.term_months
    ).first()
    
    if not interest_range:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Loan term of {loan_data.term_months} month(s) is not available for your credit rating tier."
        )
    
    # Update application
    application.amount = loan_amount
    application.term_months = loan_data.term_months
    application.notes = loan_data.notes
    application.cycle_id = cycle_uuid
    if loan_data.borrowing_date:
        try:
            borrow_dt = date.fromisoformat(loan_data.borrowing_date)
            application.application_date = datetime.combine(borrow_dt, datetime.min.time())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid borrowing_date format. Use YYYY-MM-DD.",
            )
    
    db.commit()
    db.refresh(application)
    
    return {
        "message": "Loan application updated successfully",
        "application_id": str(application.id)
    }


@router.get("/loans/current")
def get_current_loan(
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db)
):
    """Get current active loan with payment breakdown (interest vs principal paid).
    Available to all authenticated users except admin."""
    from app.models.transaction import LoanStatus
    from decimal import Decimal
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return None
    
    # Get active loans (APPROVED, DISBURSED, or OPEN)
    active_loans = db.query(Loan).filter(
        Loan.member_id == member_profile.id,
        Loan.loan_status.in_([LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN])
    ).order_by(Loan.created_at.desc()).all()
    
    if not active_loans:
        return None
    
    # Get the most recent active loan
    loan = active_loans[0]
    
    # Compute payment history from approved declarations.
    # Declarations are the authoritative payment record: when a deposit is approved,
    # declared_loan_repayment = principal paid, declared_interest_on_loan = interest paid.
    # This covers both pre-fix data (no Repayment rows) and post-fix data equally.
    from app.models.transaction import Declaration, DeclarationStatus
    from sqlalchemy import or_

    decl_query = db.query(Declaration).filter(
        Declaration.member_id == member_profile.id,
        Declaration.status == DeclarationStatus.APPROVED,
        or_(
            Declaration.declared_loan_repayment > 0,
            Declaration.declared_interest_on_loan > 0,
        ),
    )
    if loan.disbursement_date:
        decl_query = decl_query.filter(
            Declaration.effective_month >= loan.disbursement_date
        )
    paid_declarations = decl_query.order_by(Declaration.effective_month.asc()).all()

    total_principal_paid = Decimal("0.00")
    total_interest_paid = Decimal("0.00")
    repayment_items = []
    for decl in paid_declarations:
        principal = decl.declared_loan_repayment or Decimal("0.00")
        interest = decl.declared_interest_on_loan or Decimal("0.00")
        total_principal_paid += principal
        total_interest_paid += interest
        repayment_items.append({
            "id": f"decl_{decl.id}",
            "date": decl.effective_month.isoformat(),
            "principal": float(principal),
            "interest": float(interest),
            "total": float(principal + interest),
        })

    outstanding_balance = max(Decimal("0.00"), loan.loan_amount - total_principal_paid)

    rate = float(loan.percentage_interest or 0)
    interest_expected = Decimal(str(
        float(loan.loan_amount) * (rate / 100)
    )) if rate > 0 else Decimal("0.00")

    # Auto-close the loan when principal AND interest are fully repaid
    if outstanding_balance <= Decimal("0.01") and total_interest_paid >= interest_expected:
        if loan.loan_status != LoanStatus.CLOSED:
            loan.loan_status = LoanStatus.CLOSED
            db.commit()
            db.refresh(loan)

    # Compute maturity date from disbursement + term months
    maturity_date = None
    if loan.disbursement_date and loan.number_of_instalments:
        try:
            from dateutil.relativedelta import relativedelta
            term = int(loan.number_of_instalments)
            maturity_date = (loan.disbursement_date + relativedelta(months=term)).isoformat()
        except (ValueError, TypeError):
            pass

    interest_outstanding = max(Decimal("0.00"), interest_expected - total_interest_paid)

    return {
        "id": str(loan.id),
        "cycle_id": str(loan.cycle_id) if loan.cycle_id else None,
        "loan_amount": float(loan.loan_amount),
        "term_months": loan.number_of_instalments or "N/A",
        "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
        "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
        "maturity_date": maturity_date,
        "status": loan.loan_status.value,
        "total_principal_paid": float(total_principal_paid),
        "total_interest_paid": float(total_interest_paid),
        "total_paid": float(total_principal_paid + total_interest_paid),
        "outstanding_balance": float(outstanding_balance),
        "interest_expected": float(interest_expected),
        "interest_outstanding": float(interest_outstanding),
        "repayments": repayment_items,
    }


@router.get("/loans/{loan_id}/early-payoff-options")
def get_loan_early_payoff_options(
    loan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the term-shortening options available to the member for early
    loan payoff.

    Rules (from user requirements):
      * Loan must belong to the current user and be active
        (APPROVED / DISBURSED / OPEN).
      * ``elapsed_months`` counts full calendar months between the loan's
        disbursement month and the current month. If disbursed in April
        and today is May, elapsed = 1.
      * A valid new term is any integer N where
        ``elapsed_months <= N < original_term_months`` — the loan lasted
        at least the time already used but strictly less than the
        original commitment.
      * For each candidate N, the interest rate is looked up from the
        member's credit-rating × N-month range. Terms without a
        configured rate are hidden — the member can only pick from what
        the schedule officially prices.
      * The endpoint is view-only; nothing is committed.

    Response shape:
        {
          "loan": { id, amount, current_term_months, current_rate,
                    current_expected_interest, interest_already_paid,
                    interest_outstanding, disbursement_date, cycle_id },
          "elapsed_months": int,
          "eligible": bool,
          "reason_if_ineligible": str | None,
          "options": [
             { "new_term_months": "1",
               "new_percentage_interest": 6.0,
               "new_expected_interest": 600.0,
               "interest_delta": -200.0 },
             ...
          ]
        }
    """
    from app.models.transaction import LoanStatus, Loan, Repayment
    from app.models.policy import (
        MemberCreditRating, CreditRatingInterestRange,
    )
    from decimal import Decimal
    from datetime import date as _date

    try:
        loan_uuid = UUID(loan_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid loan_id")

    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")

    loan = db.query(Loan).filter(Loan.id == loan_uuid).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != member_profile.id:
        raise HTTPException(
            status_code=403,
            detail="You can only inspect early-payoff options for your own loans",
        )
    if loan.loan_status not in (LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN):
        raise HTTPException(
            status_code=400,
            detail=f"Loan is not active (status: {loan.loan_status.value if loan.loan_status else 'unknown'})",
        )

    current_amount = Decimal(str(loan.loan_amount or 0))
    current_rate = Decimal(str(loan.percentage_interest or 0))
    current_expected_interest = (current_amount * current_rate / Decimal("100")).quantize(Decimal("0.01"))

    try:
        original_term = int((loan.number_of_instalments or "").strip())
    except (TypeError, ValueError):
        original_term = 0

    interest_paid = Decimal("0.00")
    for rep in loan.repayments:
        interest_paid += Decimal(str(rep.interest_amount or 0))
    interest_outstanding = max(Decimal("0.00"), current_expected_interest - interest_paid)

    disbursement_date = loan.disbursement_date
    today = _date.today()
    elapsed_months = 0
    if disbursement_date:
        elapsed_months = (
            (today.year - disbursement_date.year) * 12
            + (today.month - disbursement_date.month)
        )
        if elapsed_months < 0:
            elapsed_months = 0

    loan_summary = {
        "id": str(loan.id),
        "amount": float(current_amount),
        "current_term_months": loan.number_of_instalments,
        "current_rate": float(current_rate),
        "current_expected_interest": float(current_expected_interest),
        "interest_already_paid": float(interest_paid),
        "interest_outstanding": float(interest_outstanding),
        "disbursement_date": disbursement_date.isoformat() if disbursement_date else None,
        "cycle_id": str(loan.cycle_id) if loan.cycle_id else None,
    }

    # Eligibility gates: the loan must have a disbursement date, an
    # original term > 1, and at least one month must have elapsed. Members
    # can't shrink a loan to less than the time already used.
    if not disbursement_date:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": "Loan has not been disbursed yet.",
            "options": [],
        }
    if original_term <= 1:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": "Loan is already a 1-month loan — nothing to shorten.",
            "options": [],
        }
    if elapsed_months < 1:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": (
                "Loan was disbursed this month — early payoff opens once you're at least one month in."
            ),
            "options": [],
        }
    if elapsed_months >= original_term:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": (
                "Loan has already reached its original maturity — no early-payoff to offer."
            ),
            "options": [],
        }

    # Look up the member's credit rating for this loan's cycle so the new
    # rate follows the same schedule as their original loan pricing.
    rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == loan.cycle_id,
    ).first()
    if not rating:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": (
                "No credit rating configured for this cycle — cannot look up a new rate."
            ),
            "options": [],
        }

    # Build candidate new terms: from elapsed_months up to original_term - 1.
    # Only include terms with a configured rate on the schedule.
    options = []
    for candidate in range(elapsed_months, original_term):
        rng = db.query(CreditRatingInterestRange).filter(
            CreditRatingInterestRange.tier_id == rating.tier_id,
            CreditRatingInterestRange.cycle_id == loan.cycle_id,
            CreditRatingInterestRange.term_months == str(candidate),
        ).first()
        if not rng:
            continue
        new_rate = Decimal(str(rng.effective_rate_percent or 0))
        new_expected = (current_amount * new_rate / Decimal("100")).quantize(Decimal("0.01"))
        interest_delta = (new_expected - current_expected_interest).quantize(Decimal("0.01"))
        options.append({
            "new_term_months": str(candidate),
            "new_percentage_interest": float(new_rate),
            "new_expected_interest": float(new_expected),
            "interest_delta": float(interest_delta),
        })

    reason = None
    if not options:
        reason = (
            "No shorter term has a configured interest rate for your credit rating. "
            "Ask the chairman to update the rate schedule if you need an early payoff option."
        )

    return {
        "loan": loan_summary,
        "elapsed_months": elapsed_months,
        "eligible": bool(options),
        "reason_if_ineligible": reason,
        "options": options,
    }


class PayLoanEarlyRequest(BaseModel):
    new_term_months: str


@router.post("/loans/{loan_id}/pay-early")
def pay_loan_early(
    loan_id: str,
    body: PayLoanEarlyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Shorten an active loan to the selected term.

    Server-side re-validates against the same rules as the
    early-payoff-options endpoint: term must be within
    [elapsed_months, original_term - 1] AND have a rate configured on the
    member's credit-rating × term schedule for the loan's cycle. The rate
    is not accepted from the client — it's looked up server-side to
    prevent tampering.

    On success:
      * ``loan.number_of_instalments`` and ``loan.percentage_interest``
        are updated in place via the existing ``edit_loan_terms`` service.
      * A corrective JE is posted for the interest delta so the ledger
        stays in sync (same behaviour as the treasurer's Edit loan terms
        flow — reuses that machinery).
      * Full audit line lands on the JE + audit log.
    """
    from app.models.transaction import LoanStatus, Loan
    from app.models.policy import MemberCreditRating, CreditRatingInterestRange
    from app.services.loan_repair import edit_loan_terms
    from decimal import Decimal
    from datetime import date as _date

    try:
        loan_uuid = UUID(loan_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid loan_id")

    if not body.new_term_months or not body.new_term_months.strip():
        raise HTTPException(status_code=400, detail="new_term_months is required")
    new_term = body.new_term_months.strip()
    try:
        new_term_int = int(new_term)
    except ValueError:
        raise HTTPException(status_code=400, detail="new_term_months must be a positive integer")
    if new_term_int < 1:
        raise HTTPException(status_code=400, detail="new_term_months must be at least 1")

    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")

    loan = db.query(Loan).filter(Loan.id == loan_uuid).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only pay off your own loans early")
    if loan.loan_status not in (LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN):
        raise HTTPException(status_code=400, detail="Loan is not active")

    try:
        original_term = int((loan.number_of_instalments or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Loan has no valid original term to shorten")
    if new_term_int >= original_term:
        raise HTTPException(
            status_code=400,
            detail=f"New term ({new_term_int}) must be shorter than the current term ({original_term}).",
        )

    today = _date.today()
    elapsed_months = 0
    if loan.disbursement_date:
        elapsed_months = (
            (today.year - loan.disbursement_date.year) * 12
            + (today.month - loan.disbursement_date.month)
        )
        if elapsed_months < 0:
            elapsed_months = 0
    if new_term_int < elapsed_months:
        raise HTTPException(
            status_code=400,
            detail=(
                f"New term ({new_term_int}) is less than the {elapsed_months} months "
                "already elapsed — pick a term at least as long as the time you've been in the loan."
            ),
        )

    # Rate is server-side — look up the officially configured rate for
    # this member × new term. If no row exists, the option isn't valid.
    rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == loan.cycle_id,
    ).first()
    if not rating:
        raise HTTPException(
            status_code=400,
            detail="No credit rating configured for this loan's cycle.",
        )
    rng = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == rating.tier_id,
        CreditRatingInterestRange.cycle_id == loan.cycle_id,
        CreditRatingInterestRange.term_months == new_term,
    ).first()
    if not rng:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No configured interest rate for a {new_term}-month loan under your credit rating."
            ),
        )
    new_rate = Decimal(str(rng.effective_rate_percent or 0))

    reason = (
        f"Member-initiated early payoff — original term "
        f"{loan.number_of_instalments}mo shortened to {new_term}mo at {new_rate}% "
        f"(from credit-rating × term schedule)."
    )

    try:
        result = edit_loan_terms(
            db=db,
            loan_id=loan.id,
            new_term_months=new_term,
            new_percentage_interest=new_rate,
            reason=reason,
            user_id=current_user.id,
            new_loan_amount=None,  # amount stays fixed
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "member",
        action="Loan shortened via Pay Loan Early",
        details=(
            f"loan={str(loan.id)[:8]} term={loan.number_of_instalments}→{new_term}mo "
            f"rate={result.get('old_percentage_interest')}→{result.get('new_percentage_interest')} "
            f"interest_delta={result.get('interest_delta')}"
        ),
    )
    return result


@router.get("/loans/{loan_id}/extend-options")
def get_loan_extend_options(
    loan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the term-lengthening options available to the member.

    Mirror of ``get_loan_early_payoff_options`` for the OTHER direction:
    a member with a 1-month loan (or any active loan) can extend to a
    longer term, provided:
      * the loan is theirs and active (APPROVED / DISBURSED / OPEN)
      * a longer term has a rate configured on the member's credit-rating
        × term schedule for the loan's cycle

    The list of extension candidates is derived from what the schedule
    actually prices — there's no arbitrary upper bound. Any tier × cycle
    row with ``term_months > current_term`` is a valid option.
    Rates are locked to the schedule; nothing is typed by hand.

    Interest usually goes UP for a longer loan (longer term = higher
    rate) so the corrective JE lands on the same INTEREST_RECEIVABLE /
    INTEREST_INCOME accounts, in the opposite direction from the
    early-payoff case.
    """
    from app.models.transaction import LoanStatus, Loan
    from app.models.policy import MemberCreditRating, CreditRatingInterestRange
    from decimal import Decimal
    from datetime import date as _date

    try:
        loan_uuid = UUID(loan_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid loan_id")

    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")

    loan = db.query(Loan).filter(Loan.id == loan_uuid).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != member_profile.id:
        raise HTTPException(
            status_code=403,
            detail="You can only inspect extension options for your own loans",
        )
    if loan.loan_status not in (LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN):
        raise HTTPException(
            status_code=400,
            detail=f"Loan is not active (status: {loan.loan_status.value if loan.loan_status else 'unknown'})",
        )

    current_amount = Decimal(str(loan.loan_amount or 0))
    current_rate = Decimal(str(loan.percentage_interest or 0))
    current_expected_interest = (current_amount * current_rate / Decimal("100")).quantize(Decimal("0.01"))
    interest_paid = Decimal("0.00")
    for rep in loan.repayments:
        interest_paid += Decimal(str(rep.interest_amount or 0))
    interest_outstanding = max(Decimal("0.00"), current_expected_interest - interest_paid)

    try:
        original_term = int((loan.number_of_instalments or "").strip())
    except (TypeError, ValueError):
        original_term = 0

    disbursement_date = loan.disbursement_date
    today = _date.today()
    elapsed_months = 0
    if disbursement_date:
        elapsed_months = (
            (today.year - disbursement_date.year) * 12
            + (today.month - disbursement_date.month)
        )
        if elapsed_months < 0:
            elapsed_months = 0

    loan_summary = {
        "id": str(loan.id),
        "amount": float(current_amount),
        "current_term_months": loan.number_of_instalments,
        "current_rate": float(current_rate),
        "current_expected_interest": float(current_expected_interest),
        "interest_already_paid": float(interest_paid),
        "interest_outstanding": float(interest_outstanding),
        "disbursement_date": disbursement_date.isoformat() if disbursement_date else None,
        "cycle_id": str(loan.cycle_id) if loan.cycle_id else None,
    }

    if original_term <= 0:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": "Loan has no valid current term to extend from.",
            "options": [],
        }

    # Look up the member's credit-rating × cycle so extensions are priced
    # off the same schedule the original loan was.
    rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == loan.cycle_id,
    ).first()
    if not rating:
        return {
            "loan": loan_summary,
            "elapsed_months": elapsed_months,
            "eligible": False,
            "reason_if_ineligible": (
                "No credit rating configured for this cycle — cannot look up a new rate."
            ),
            "options": [],
        }

    # Every schedule row where term_months > original_term is a candidate.
    # Sort numerically (schedules store term_months as strings).
    ranges = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == rating.tier_id,
        CreditRatingInterestRange.cycle_id == loan.cycle_id,
    ).all()

    options = []
    for rng in ranges:
        try:
            candidate = int((rng.term_months or "").strip())
        except (TypeError, ValueError):
            continue
        if candidate <= original_term:
            continue
        new_rate = Decimal(str(rng.effective_rate_percent or 0))
        new_expected = (current_amount * new_rate / Decimal("100")).quantize(Decimal("0.01"))
        interest_delta = (new_expected - current_expected_interest).quantize(Decimal("0.01"))
        options.append({
            "new_term_months": str(candidate),
            "new_percentage_interest": float(new_rate),
            "new_expected_interest": float(new_expected),
            "interest_delta": float(interest_delta),
        })
    options.sort(key=lambda o: int(o["new_term_months"]))

    reason = None
    if not options:
        reason = (
            "No longer term has a configured interest rate for your credit rating. "
            "Ask the chairman to update the rate schedule if a longer term is needed."
        )

    return {
        "loan": loan_summary,
        "elapsed_months": elapsed_months,
        "eligible": bool(options),
        "reason_if_ineligible": reason,
        "options": options,
    }


class ExtendLoanRequest(BaseModel):
    new_term_months: str


@router.post("/loans/{loan_id}/extend")
def extend_loan(
    loan_id: str,
    body: ExtendLoanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lengthen an active loan to the selected term.

    Mirror of ``pay_loan_early`` for the extend direction. Server-side
    re-validates the term > current_term rule and re-fetches the rate
    from the schedule (never accepted from the client). Delegates to the
    existing ``edit_loan_terms`` service so the corrective JE for the
    interest delta lands under the loan's disbursement month using the
    same accounting machinery the treasurer already uses.
    """
    from app.models.transaction import LoanStatus, Loan
    from app.models.policy import MemberCreditRating, CreditRatingInterestRange
    from app.services.loan_repair import edit_loan_terms
    from decimal import Decimal

    try:
        loan_uuid = UUID(loan_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid loan_id")

    if not body.new_term_months or not body.new_term_months.strip():
        raise HTTPException(status_code=400, detail="new_term_months is required")
    new_term = body.new_term_months.strip()
    try:
        new_term_int = int(new_term)
    except ValueError:
        raise HTTPException(status_code=400, detail="new_term_months must be a positive integer")
    if new_term_int < 1:
        raise HTTPException(status_code=400, detail="new_term_months must be at least 1")

    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")

    loan = db.query(Loan).filter(Loan.id == loan_uuid).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only extend your own loans")
    if loan.loan_status not in (LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN):
        raise HTTPException(status_code=400, detail="Loan is not active")

    try:
        original_term = int((loan.number_of_instalments or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Loan has no valid original term to extend")
    if new_term_int <= original_term:
        raise HTTPException(
            status_code=400,
            detail=f"New term ({new_term_int}) must be longer than the current term ({original_term}).",
        )

    rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_profile.id,
        MemberCreditRating.cycle_id == loan.cycle_id,
    ).first()
    if not rating:
        raise HTTPException(
            status_code=400,
            detail="No credit rating configured for this loan's cycle.",
        )
    rng = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == rating.tier_id,
        CreditRatingInterestRange.cycle_id == loan.cycle_id,
        CreditRatingInterestRange.term_months == new_term,
    ).first()
    if not rng:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No configured interest rate for a {new_term}-month loan under your credit rating."
            ),
        )
    new_rate = Decimal(str(rng.effective_rate_percent or 0))

    reason = (
        f"Member-initiated loan extension — original term "
        f"{loan.number_of_instalments}mo lengthened to {new_term}mo at {new_rate}% "
        f"(from credit-rating × term schedule)."
    )

    try:
        result = edit_loan_terms(
            db=db,
            loan_id=loan.id,
            new_term_months=new_term,
            new_percentage_interest=new_rate,
            reason=reason,
            user_id=current_user.id,
            new_loan_amount=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "member",
        action="Loan extended via member request",
        details=(
            f"loan={str(loan.id)[:8]} term={loan.number_of_instalments}→{new_term}mo "
            f"rate={result.get('old_percentage_interest')}→{result.get('new_percentage_interest')} "
            f"interest_delta={result.get('interest_delta')}"
        ),
    )
    return result


@router.get("/loans")
def get_my_loans(
    current_user: User = Depends(require_not_admin()),
    db: Session = Depends(get_db)
):
    """Get my loan applications and approved loans. 
    Avoids duplicates: if an application has been approved and has a Loan record, only show the Loan.
    Available to all authenticated users except admin."""
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        # Return empty list if no member profile exists
        return []
    
    # Get all loans (including closed/paid off loans for history)
    # These take precedence over applications - if an application was approved, show the Loan instead
    loans = db.query(Loan).filter(
        Loan.member_id == member_profile.id
    ).order_by(Loan.created_at.desc()).all()
    
    # Get set of application IDs that have been converted to loans
    approved_application_ids = {loan.application_id for loan in loans if loan.application_id}
    
    # Get loan applications that haven't been converted to loans yet
    if approved_application_ids:
        applications = db.query(LoanApplication).filter(
            LoanApplication.member_id == member_profile.id,
            ~LoanApplication.id.in_(approved_application_ids)
        ).order_by(LoanApplication.application_date.desc()).all()
    else:
        applications = db.query(LoanApplication).filter(
            LoanApplication.member_id == member_profile.id
        ).order_by(LoanApplication.application_date.desc()).all()
    
    # Combine and format
    result = []
    
    # Add applications that haven't been approved yet (no corresponding Loan)
    for app in applications:
        result.append({
            "id": str(app.id),
            "cycle_id": str(app.cycle_id),
            "amount": float(app.amount),
            "term_months": app.term_months,
            "notes": app.notes,
            "status": app.status.value if hasattr(app.status, 'value') else str(app.status),
            "application_date": app.application_date.isoformat() if app.application_date else None,
            "type": "application"
        })
    
    # Add loans (these replace approved applications)
    from calendar import monthrange as _monthrange
    from datetime import date as _date_cls
    for loan in loans:
        # Map status: OPEN -> active, others stay as-is
        status_value = loan.loan_status.value if hasattr(loan.loan_status, 'value') else str(loan.loan_status)
        if status_value == "open":
            status_display = "active"
        else:
            status_display = status_value

        # Compute maturity_date = disbursement_date + term_months (with month-end clamp).
        maturity_iso = None
        if loan.disbursement_date and loan.number_of_instalments:
            try:
                term = int(loan.number_of_instalments)
                d = loan.disbursement_date
                new_month = d.month - 1 + term
                new_year = d.year + new_month // 12
                new_month = new_month % 12 + 1
                last_day = _monthrange(new_year, new_month)[1]
                new_day = min(d.day, last_day)
                maturity_iso = _date_cls(new_year, new_month, new_day).isoformat()
            except (ValueError, TypeError):
                pass

        result.append({
            "id": str(loan.id),
            "cycle_id": str(loan.cycle_id) if loan.cycle_id else None,
            "amount": float(loan.loan_amount),
            "term_months": loan.number_of_instalments or "N/A",
            "status": status_display,
            "application_date": loan.disbursement_date.isoformat() if loan.disbursement_date else (loan.created_at.isoformat() if loan.created_at else None),
            "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
            "maturity_date": maturity_iso,
            "type": "loan",
        })
    
    # Sort by date (most recent first)
    result.sort(key=lambda x: x.get("application_date") or "", reverse=True)
    
    return result


@router.post("/deposits/proof")
def upload_deposit_proof(
    file: UploadFile = File(...),
    amount: float = None,
    reference: str = None,
    declaration_id: str = None,
    cycle_id: str = None,
    current_user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    """Upload proof of payment."""
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile or member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Member account is not active")
    
    # Save file
    upload_dir = "uploads/deposits"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{member_profile.id}_{file.filename}")
    
    with open(file_path, "wb") as f:
        content = file.file.read()
        f.write(content)
    
    deposit_proof = DepositProof(
        member_id=member_profile.id,
        upload_path=file_path,
        amount=Decimal(str(amount)) if amount else Decimal("0.00"),
        reference=reference,
        declaration_id=declaration_id,
        cycle_id=cycle_id
    )
    db.add(deposit_proof)
    db.commit()
    db.refresh(deposit_proof)
    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "member",
        action="Deposit proof submitted",
        details=f"amount=K {amount or 0}"
    )
    return {"message": "Deposit proof uploaded successfully", "deposit_id": str(deposit_proof.id)}


@router.get("/statement")
def get_statement(
    current_user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    """Get account statement from ledger."""
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=404, detail="Member profile not found")
    
    # Get journal entries for member's accounts
    from app.models.ledger import LedgerAccount, JournalEntry, JournalLine
    member_accounts = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_profile.id
    ).all()
    
    account_ids = [acc.id for acc in member_accounts]
    journal_entries = db.query(JournalEntry).join(JournalLine).filter(
        JournalLine.ledger_account_id.in_(account_ids)
    ).distinct().order_by(JournalEntry.entry_date.desc()).all()
    
    return {
        "member_id": str(member_profile.id),
        "entries": [
            {
                "entry_id": str(entry.id),
                "date": entry.entry_date.isoformat(),
                "description": entry.description
            }
            for entry in journal_entries
        ]
    }


@router.get("/transactions")
def get_account_transactions(
    type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get transaction history for a specific account type.
    
    Types: savings, penalties, social_fund, admin_fund
    """
    from typing import Literal
    from app.models.ledger import LedgerAccount, JournalEntry, JournalLine
    from app.models.transaction import DepositProof, DepositApproval
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=404, detail="Member profile not found")
    
    valid_types = ["savings", "penalties", "social_fund", "admin_fund"]
    if type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type. Must be one of: {', '.join(valid_types)}"
        )
    
    transactions = []
    
    try:
        if type == "savings":
            from app.models.transaction import Declaration, DeclarationStatus, DepositProof, DepositApproval
            
            # Query approved deposits via DepositApproval → DepositProof
            # deposit_proof.amount is the full total (all components)
            deposit_approvals = db.query(DepositApproval).join(
                DepositProof, DepositApproval.deposit_proof_id == DepositProof.id
            ).join(
                JournalEntry, DepositApproval.journal_entry_id == JournalEntry.id
            ).filter(
                DepositProof.member_id == member_profile.id,
                JournalEntry.reversed_by.is_(None)
            ).order_by(JournalEntry.entry_date.desc()).all()

            for da in deposit_approvals:
                deposit = da.deposit_proof
                declaration = deposit.declaration if deposit else None

                if declaration:
                    date_str = declaration.effective_month.isoformat()
                    description = f"Deposit approved for {declaration.effective_month.strftime('%B %Y')} declaration"
                else:
                    date_str = da.journal_entry.entry_date.isoformat()
                    description = "Approved deposit"

                transactions.append({
                    "id": str(da.id),
                    "date": date_str,
                    "description": description,
                    "debit": 0.0,
                    "credit": float(deposit.amount),
                    "amount": float(deposit.amount)
                })
            
            # Add declarations as debit entries (informational - shows what the member
            # declared for the month). We include any declaration with a non-zero
            # declared savings amount regardless of approval state — that way the
            # statement keeps showing the declaration on the left even when the
            # corresponding deposit was rejected or reversed (in which case the
            # right-hand "Approved Deposit" column simply shows blank).
            # Include a declaration if ANY component was declared (not just
            # savings). A declaration of "K50 penalty + K1,000 interest" with
            # K0 savings was previously hidden, leaving its approved deposit
            # orphaned on the right with no declaration column on the left.
            from sqlalchemy import or_ as _or_
            declarations = db.query(Declaration).filter(
                Declaration.member_id == member_profile.id,
                _or_(
                    Declaration.declared_savings_amount > 0,
                    Declaration.declared_social_fund > 0,
                    Declaration.declared_admin_fund > 0,
                    Declaration.declared_penalties > 0,
                    Declaration.declared_loan_repayment > 0,
                    Declaration.declared_interest_on_loan > 0,
                ),
            ).order_by(Declaration.created_at.desc()).all()
            
            from app.services.accounting import compute_posted_breakdown as _posted_bd
            from app.services.accounting import get_reconciliation_notes as _recon_notes

            # -------------------------------------------------------------
            # Precompute per-declaration "ghost" penalty amounts via the
            # same greedy carry-back matcher used by the compliance audit.
            # Each declaration's posted-penalty is then set to:
            #     posted.penalty = declared_penalty - ghost
            # so a fully-unexplained month (December K50 declared, no
            # matching PenaltyRecord) shows K50 → K0 crossed, while a
            # month backed by a real charge (July K150 with Emergency
            # Loan K150) stays at K150 uncrossed.
            # -------------------------------------------------------------
            from app.models.transaction import PenaltyRecord as _PRG, PenaltyRecordStatus as _PRGS
            from app.services.transaction import _extract_effective_month_from_notes as _eff_g
            _live_pen_statuses_g = {
                _PRGS.APPROVED.value, _PRGS.PAID.value,
                _PRGS.REVERSAL_PENDING.value, _PRGS.PENDING.value,
            }
            _live_by_month_g: dict = {}
            for _p in db.query(_PRG).filter(_PRG.member_id == member_profile.id).all():
                _sv = _p.status.value if isinstance(_p.status, _PRGS) else _p.status
                if _sv not in _live_pen_statuses_g:
                    continue
                _e = _eff_g(_p.notes or "") if _p.notes else None
                if not _e and _p.date_issued:
                    _e = date(_p.date_issued.year, _p.date_issued.month, 1)
                if not _e:
                    continue
                _f = float(_p.penalty_type.fee_amount) if _p.penalty_type and _p.penalty_type.fee_amount else 0.0
                _live_by_month_g[(_e.year, _e.month)] = _live_by_month_g.get((_e.year, _e.month), 0.0) + _f
            # Ghost per declaration id — greedy consume with 1-month carry-back
            # over declarations ordered ascending by effective_month.
            _remaining_g = dict(_live_by_month_g)
            _ghost_by_decl_id: dict = {}
            for _d in sorted(
                [d for d in declarations if float(d.declared_penalties or 0) > 0],
                key=lambda x: x.effective_month,
            ):
                _decl = float(_d.declared_penalties or 0)
                _kc = (_d.effective_month.year, _d.effective_month.month)
                _kp = (_d.effective_month.year - 1, 12) if _d.effective_month.month == 1 else (_d.effective_month.year, _d.effective_month.month - 1)
                _ac = _remaining_g.get(_kc, 0.0)
                _ap = _remaining_g.get(_kp, 0.0)
                _tc = min(_decl, _ac)
                _tp = min(_decl - _tc, _ap)
                _remaining_g[_kc] = _ac - _tc
                _remaining_g[_kp] = _ap - _tp
                _ghost_by_decl_id[_d.id] = max(0.0, round(_decl - (_tc + _tp), 2))

            for declaration in declarations:
                posted_items = _posted_bd(
                    db, member_profile.id,
                    declaration.effective_month.year,
                    declaration.effective_month.month,
                )
                # Adjust penalty: posted = declared - ghost. Fully-ghost
                # months show "declared → 0 posted"; partially-explained
                # months show the amount actually backed by real charges.
                _decl_pen = float(declaration.declared_penalties or 0)
                _ghost = _ghost_by_decl_id.get(declaration.id, 0.0)
                posted_items["penalty"] = max(0.0, _decl_pen - _ghost)
                declared_items_chk = {
                    "savings": float(declaration.declared_savings_amount or 0),
                    "social_fund": float(declaration.declared_social_fund or 0),
                    "admin_fund": float(declaration.declared_admin_fund or 0),
                    "penalty": float(declaration.declared_penalties or 0),
                }
                has_reconciliation_discrepancy = (
                    declaration.status == DeclarationStatus.APPROVED
                    and any(
                        abs(posted_items[k] - declared_items_chk[k]) > 0.01
                        for k in declared_items_chk
                    )
                )
                reconciliation_notes = (
                    _recon_notes(
                        db, member_profile.id,
                        declaration.effective_month.year,
                        declaration.effective_month.month,
                    )
                    if has_reconciliation_discrepancy
                    else []
                )
                transactions.append({
                    "id": f"declaration_{declaration.id}",
                    "date": declaration.effective_month.isoformat(),
                    "description": f"Declaration for {declaration.effective_month.strftime('%B %Y')}",
                    "debit": float(declaration.declared_savings_amount or 0),
                    "credit": 0.0,
                    "amount": float(declaration.declared_savings_amount or 0),
                    "is_declaration": True,
                    "declaration_items": {
                        "savings_amount":   float(declaration.declared_savings_amount or 0),
                        "social_fund":      float(declaration.declared_social_fund or 0),
                        "admin_fund":       float(declaration.declared_admin_fund or 0),
                        "penalties":        float(declaration.declared_penalties or 0),
                        "loan_repayment":   float(declaration.declared_loan_repayment or 0),
                        "interest_on_loan": float(declaration.declared_interest_on_loan or 0),
                    },
                    "posted_items": posted_items,
                    "has_reconciliation_discrepancy": has_reconciliation_discrepancy,
                    "reconciliation_notes": reconciliation_notes,
                })
            
            # Excess-contribution / split / reverse JEs are intentionally NOT
            # surfaced as separate rows. They're internal reclassifications of
            # money already counted under the originating deposit, so summing
            # them into the "Approved Deposit" column would double-count.
            # Their effect is reflected via the declaration row's posted_items
            # annotation ("Savings: K1,950 declared → K2,000 posted").

            # Sort all transactions by date (most recent first)
            transactions.sort(key=lambda x: x["date"], reverse=True)

            # -------------------------------------------------------------
            # Penalty reversals — surface each one as a savings-side credit
            # entry so the member sees the refund on their statement with a
            # clear narration. Reversal accounting: Dr PENALTY_INCOME /
            # Cr MEM_SAV — the fee amount lands back in the member's
            # savings, so it's a genuine "Approved Deposit"-style credit
            # from the member's point of view.
            # -------------------------------------------------------------
            from app.models.transaction import PenaltyRecord as _PR, PenaltyRecordStatus as _PRS, PenaltyType as _PT
            _reversed_penalties = (
                db.query(_PR)
                .filter(
                    _PR.member_id == member_profile.id,
                    _PR.status == _PRS.REVERSED.value,
                )
                .all()
            )
            penalty_reversals_dto = []
            from app.services.transaction import _extract_effective_month_from_notes
            for _p in _reversed_penalties:
                _ptype = _p.penalty_type
                _fee = float(_ptype.fee_amount) if _ptype and _ptype.fee_amount is not None else 0.0
                _pname = (_ptype.name if _ptype else "") or "Penalty"
                if _fee <= 0:
                    continue
                # Bucket the reversal under the ORIGINAL penalty's
                # date_issued month — that's the month the charge actually
                # hit the member's savings, so the refund logically belongs
                # to the same row. Falls back to reversed_at if date_issued
                # is missing.
                _ref_dt = _p.date_issued or _p.reversed_at
                _iso = _ref_dt.isoformat() if _ref_dt else None
                # Push as a transaction so the monthly table can render it.
                transactions.append({
                    "id": f"penalty_reversal_{_p.id}",
                    "date": _iso or "",
                    "description": (
                        f"Penalty refund — {_pname} K{_fee:.2f} reversed"
                    ),
                    "debit": 0.0,
                    "credit": _fee,
                    "amount": _fee,
                    "is_penalty_reversal": True,
                    "reversal_reason": _p.reversal_reason,
                    "penalty_type_name": _pname,
                    "fee_amount": _fee,
                    "reversed_at": _p.reversed_at.isoformat() if _p.reversed_at else None,
                    "original_date_issued": _p.date_issued.isoformat() if _p.date_issued else None,
                })
                penalty_reversals_dto.append({
                    "id": str(_p.id),
                    "penalty_type_name": _pname,
                    "fee_amount": _fee,
                    "reversed_at": _p.reversed_at.isoformat() if _p.reversed_at else None,
                    "reversal_reason": _p.reversal_reason,
                    "original_date_issued": _p.date_issued.isoformat() if _p.date_issued else None,
                })

            # -------------------------------------------------------------
            # Unexplained declared-penalty reversals — posted via the
            # bulk compliance action. These have no PenaltyRecord; they
            # exist only as JEs with source_type =
            # "unexplained_penalty_reversal", source_ref = declaration id,
            # dealing_month = declaration effective_month. Surface each
            # as an `is_penalty_reversal` transaction bucketed under the
            # declaration month, so the Statement's existing fold-into-row
            # logic renders the strikethrough and "refunded to savings"
            # line automatically.
            # -------------------------------------------------------------
            from app.models.ledger import JournalEntry as _JE2, JournalLine as _JL2
            from app.models.transaction import Declaration as _D2
            _savings_acc = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_profile.id,
                LedgerAccount.account_name.ilike("%savings%"),
            ).first()
            if _savings_acc:
                _unexp_lines = (
                    db.query(_JL2)
                    .join(_JE2, _JL2.journal_entry_id == _JE2.id)
                    .filter(
                        _JL2.ledger_account_id == _savings_acc.id,
                        _JE2.source_type == "unexplained_penalty_reversal",
                        _JE2.reversed_by.is_(None),
                        _JL2.credit_amount > 0,
                    )
                    .all()
                )
                for _ln in _unexp_lines:
                    _je = _ln.journal_entry
                    _amt = float(_ln.credit_amount or 0)
                    if _amt <= 0:
                        continue
                    # Bucket under the declaration's effective month
                    # (dealing_month on the JE); fall back to entry_date.
                    _bucket_dt = _je.dealing_month or _je.entry_date
                    _iso = _bucket_dt.isoformat() if _bucket_dt else None
                    _decl_month_str = (
                        _bucket_dt.strftime("%B %Y") if _bucket_dt else ""
                    )
                    _reason = (
                        f"No compliance record explained this K{_amt:.2f} on the "
                        f"{_decl_month_str} declaration, so it was refunded to savings."
                    )
                    transactions.append({
                        "id": f"unexplained_penalty_reversal_{_je.id}",
                        "date": _iso or "",
                        "description": (
                            f"Unexplained penalty refund — K{_amt:.2f} returned to savings"
                        ),
                        "debit": 0.0,
                        "credit": _amt,
                        "amount": _amt,
                        "is_penalty_reversal": True,
                        # Flag this as a data-correction refund (not a
                        # reversal of a real penalty charge). The Statement
                        # uses this to skip subtracting it from the row's
                        # "Penalties posted" figure — the underlying
                        # PenaltyRecord charge (e.g. Emergency Loan K150)
                        # is real and should keep counting as posted; the
                        # refund is shown separately as a refund line only.
                        "is_unexplained_reversal": True,
                        "reversal_reason": _reason,
                        "penalty_type_name": "Unexplained declared penalty",
                        "fee_amount": _amt,
                        "reversed_at": _je.entry_date.isoformat() if _je.entry_date else None,
                        "original_date_issued": _iso,
                    })
                    penalty_reversals_dto.append({
                        "id": f"unexplained_{_je.id}",
                        "penalty_type_name": "Unexplained declared penalty",
                        "fee_amount": _amt,
                        "reversed_at": _je.entry_date.isoformat() if _je.entry_date else None,
                        "reversal_reason": _reason,
                        "original_date_issued": _iso,
                    })

            transactions.sort(key=lambda x: x.get("date") or "", reverse=True)

        elif type == "penalties":
            from app.models.transaction import PenaltyRecord, PenaltyRecordStatus, PenaltyType, Declaration, DeclarationStatus
            from app.models.cycle import Cycle, CyclePhase, PhaseType
            from sqlalchemy import extract
            from datetime import date as date_type
            
            # Get member's penalties account (for payments/credits)
            penalties_account = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_profile.id,
                LedgerAccount.account_name.ilike("%penalties%")
            ).first()
            
            # Get member's savings account (for penalty charges/debits)
            savings_account = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_profile.id,
                LedgerAccount.account_name.ilike("%savings%")
            ).first()
            
            # 1. Get journal lines (payment entries/credits) from penalties account
            if penalties_account:
                journal_lines = db.query(JournalLine).join(JournalEntry).filter(
                    JournalLine.ledger_account_id == penalties_account.id,
                    JournalEntry.reversed_by.is_(None)  # Exclude reversed entries
                ).order_by(JournalEntry.entry_date.desc()).all()
                
                for line in journal_lines:
                    # Handle None values safely
                    debit_val = float(line.debit_amount) if line.debit_amount is not None else 0.0
                    credit_val = float(line.credit_amount) if line.credit_amount is not None else 0.0
                    amount = debit_val if debit_val > 0 else credit_val
                    
                    transactions.append({
                        "id": str(line.id),
                        "date": line.journal_entry.entry_date.isoformat() if line.journal_entry.entry_date else None,
                        "description": line.description or line.journal_entry.description,
                        "debit": debit_val,
                        "credit": credit_val,
                        "amount": amount,
                        "is_penalty_record": False
                    })
            
            # 1b. Get journal lines (penalty charges/debits) from savings account
            # When penalties are approved, they debit the savings account
            penalty_charge_lines = []
            if savings_account:
                penalty_charge_lines = db.query(JournalLine).join(JournalEntry).filter(
                    JournalLine.ledger_account_id == savings_account.id,
                    JournalEntry.reversed_by.is_(None),  # Exclude reversed entries
                    JournalEntry.source_type == "penalty",  # Only penalty-related entries
                    JournalLine.debit_amount > 0  # Only debits (charges)
                ).order_by(JournalEntry.entry_date.desc()).all()
                
                for line in penalty_charge_lines:
                    # Get the penalty record to show details
                    penalty_record = None
                    if line.journal_entry.source_ref:
                        try:
                            penalty_uuid = UUID(line.journal_entry.source_ref)
                            penalty_record = db.query(PenaltyRecord).filter(PenaltyRecord.id == penalty_uuid).first()
                        except (ValueError, TypeError):
                            pass
                    
                    # Build description
                    description = line.description or line.journal_entry.description or "Penalty charged"
                    if penalty_record and penalty_record.penalty_type:
                        description = f"{penalty_record.penalty_type.name}"
                        if penalty_record.notes:
                            description += f" - {penalty_record.notes}"
                    
                    debit_val = float(line.debit_amount) if line.debit_amount is not None else 0.0
                    
                    transactions.append({
                        "id": f"penalty_charge_{line.id}",
                        "date": line.journal_entry.entry_date.isoformat() if line.journal_entry.entry_date else None,
                        "description": description,
                        "debit": debit_val,
                        "credit": 0.0,
                        "amount": debit_val,
                        "is_penalty_record": False,
                        "is_penalty_charge": True
                    })
            
            # 2. Get individual penalty records (PENDING and APPROVED only).
            # PAID penalties are excluded; they appear as journal lines from deposit approvals above.
            # Use text() with explicit enum casting - handle both uppercase (old) and lowercase (new) enum values
            # SQLAlchemy's SQLEnum uses enum names (PENDING) instead of values (pending), so we work around it
            penalty_records = db.query(PenaltyRecord).filter(
                PenaltyRecord.member_id == member_profile.id,
                PenaltyRecord.status.in_([PenaltyRecordStatus.PENDING, PenaltyRecordStatus.APPROVED])
            ).order_by(PenaltyRecord.date_issued.desc()).all()
            
            # Track which penalties already appear in journal lines (to avoid duplicates in penalty records section)
            # Build a set of penalty IDs that we found in journal lines above
            penalties_in_journal_lines = set()
            if savings_account:
                # Get all penalty IDs from journal lines we already processed above
                for line in penalty_charge_lines:
                    if line.journal_entry.source_ref:
                        try:
                            penalty_id = UUID(line.journal_entry.source_ref)
                            penalties_in_journal_lines.add(penalty_id)
                        except (ValueError, TypeError):
                            pass
            
            for penalty in penalty_records:
                # Skip APPROVED penalties that already appear in journal lines (to avoid duplicates)
                # Only skip if we actually found them in the journal lines section above
                # This ensures that:
                # 1. Penalties without journal entries (old data) still show in penalty records
                # 2. Penalties with journal entries that don't show in journal lines (edge cases) still show in penalty records
                if penalty.status == PenaltyRecordStatus.APPROVED and penalty.id in penalties_in_journal_lines:
                    continue
                penalty_type = penalty.penalty_type
                # Handle None values safely
                if penalty_type and penalty_type.fee_amount is not None:
                    fee_amount = float(penalty_type.fee_amount)
                else:
                    fee_amount = 0.0
                
                # Build description with penalty type name and notes
                description = penalty_type.name if penalty_type else "Penalty"
                if penalty.notes:
                    description += f" - {penalty.notes}"
                
                # Add status indicator for non-PAID penalties (show status for PENDING and APPROVED)
                if penalty.status != PenaltyRecordStatus.PAID:
                    description += f" ({penalty.status.value})"
                
                # Handle None date_issued
                date_str = penalty.date_issued.isoformat() if penalty.date_issued else None
                
                # All penalty records are shown as debits (charges)
                transactions.append({
                    "id": f"penalty_{penalty.id}",
                    "date": date_str,
                    "description": description,
                    "debit": fee_amount,
                    "credit": 0.0,
                    "amount": fee_amount,
                    "is_penalty_record": True,
                    "penalty_status": penalty.status.value
                })
            
            # Note: Late declaration penalties are now created as PenaltyRecord entries
            # automatically when declarations are created late, so they appear in section 2 above
            
            # Sort all transactions by date (most recent first)
            transactions.sort(key=lambda x: x["date"] or "", reverse=True)
        
        elif type == "social_fund":
            # Get member's social fund account (member-specific)
            member_social_fund_account = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_profile.id,
                LedgerAccount.account_name.ilike("%social fund%")
            ).first()
            
            if member_social_fund_account:
                # Get all journal lines for this member's social fund account
                journal_lines = db.query(JournalLine).join(JournalEntry).filter(
                    JournalLine.ledger_account_id == member_social_fund_account.id,
                    JournalEntry.reversed_by.is_(None)  # Exclude reversed entries
                ).order_by(JournalEntry.entry_date.desc()).all()
                
                for line in journal_lines:
                    # Determine if this is initial requirement or payment
                    is_initial = line.journal_entry.source_type == "cycle_initial_requirement"
                    is_payment = line.journal_entry.source_type == "deposit_approval"
                    
                    if is_initial:
                        # Initial required amount (debit)
                        amount = float(line.debit_amount) if line.debit_amount and line.debit_amount > 0 else 0.0
                        if amount > 0:
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": line.description or line.journal_entry.description,
                                "debit": amount,
                                "credit": 0.0,
                                "amount": amount,
                                "is_initial_requirement": True
                            })
                    elif is_payment:
                        # Payment - should be CREDIT (reduces balance due)
                        # Required amount → Debit, Payment → Credit, Balance = Debits - Credits
                        # Handle None values and Decimal comparisons properly
                        debit_val = line.debit_amount if line.debit_amount is not None else Decimal("0.00")
                        credit_val = line.credit_amount if line.credit_amount is not None else Decimal("0.00")
                        debit_amount = float(debit_val) if debit_val and debit_val > Decimal("0.00") else 0.0
                        credit_amount = float(credit_val) if credit_val and credit_val > Decimal("0.00") else 0.0

                        # For payments, prioritize credit (new correct behavior)
                        # If there's a credit, use it; otherwise fall back to debit (legacy data)
                        if credit_amount > 0:
                            amount = credit_amount
                            # Payment is a credit (reduces balance)
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": line.description or line.journal_entry.description,
                                "debit": 0.0,
                                "credit": credit_amount,
                                "amount": credit_amount,
                                "is_payment": True
                            })
                        elif debit_amount > 0:
                            # Legacy data - old payments were debited, but we'll show as credit for consistency
                            # This handles old transactions before the fix
                            amount = debit_amount
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": line.description or line.journal_entry.description,
                                "debit": 0.0,
                                "credit": debit_amount,  # Show legacy debit as credit for display consistency
                                "amount": debit_amount,
                                "is_payment": True
                            })
                    elif line.journal_entry.source_type == "excess_contribution":
                        # Excess transferred to savings (debit on fund account)
                        debit_val = float(line.debit_amount) if line.debit_amount and line.debit_amount > 0 else 0.0
                        if debit_val > 0:
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": "Overpayment transferred to Savings",
                                "debit": debit_val,
                                "credit": 0.0,
                                "amount": debit_val,
                                "is_excess_transfer": True
                            })
                    else:
                        # Treasurer corrections: splits, manual adjustments etc.
                        cred = float(line.credit_amount or 0)
                        deb = float(line.debit_amount or 0)
                        if cred == 0 and deb == 0:
                            continue
                        transactions.append({
                            "id": f"adj_{line.id}",
                            "date": line.journal_entry.entry_date.isoformat() if line.journal_entry.entry_date else None,
                            "description": line.description or line.journal_entry.description or "Treasurer adjustment",
                            "debit": deb,
                            "credit": cred,
                            "amount": cred if cred > 0 else deb,
                            "is_adjustment": True,
                            "source_type": line.journal_entry.source_type,
                        })

        elif type == "admin_fund":
            # Get member's admin fund account (member-specific)
            member_admin_fund_account = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_profile.id,
                LedgerAccount.account_name.ilike("%admin fund%")
            ).first()
            
            if member_admin_fund_account:
                # Get all journal lines for this member's admin fund account
                journal_lines = db.query(JournalLine).join(JournalEntry).filter(
                    JournalLine.ledger_account_id == member_admin_fund_account.id,
                    JournalEntry.reversed_by.is_(None)  # Exclude reversed entries
                ).order_by(JournalEntry.entry_date.desc()).all()
                
                for line in journal_lines:
                    # Determine if this is initial requirement or payment
                    is_initial = line.journal_entry.source_type == "cycle_initial_requirement"
                    is_payment = line.journal_entry.source_type == "deposit_approval"
                    
                    if is_initial:
                        # Initial required amount (debit)
                        amount = float(line.debit_amount) if line.debit_amount > 0 else 0.0
                        if amount > 0:
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": line.description or line.journal_entry.description,
                                "debit": amount,
                                "credit": 0.0,
                                "amount": amount,
                                "is_initial_requirement": True
                            })
                    elif is_payment:
                        # Payment - should be CREDIT (reduces balance due)
                        # Required amount → Debit, Payment → Credit, Balance = Debits - Credits
                        # Handle None values and Decimal comparisons properly
                        debit_val = line.debit_amount if line.debit_amount is not None else Decimal("0.00")
                        credit_val = line.credit_amount if line.credit_amount is not None else Decimal("0.00")
                        debit_amount = float(debit_val) if debit_val and debit_val > Decimal("0.00") else 0.0
                        credit_amount = float(credit_val) if credit_val and credit_val > Decimal("0.00") else 0.0

                        # For payments, prioritize credit (new correct behavior)
                        # If there's a credit, use it; otherwise fall back to debit (legacy data)
                        if credit_amount > 0:
                            amount = credit_amount
                            # Payment is a credit (reduces balance)
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": line.description or line.journal_entry.description,
                                "debit": 0.0,
                                "credit": credit_amount,
                                "amount": credit_amount,
                                "is_payment": True
                            })
                        elif debit_amount > 0:
                            # Legacy data - old payments were debited, but we'll show as credit for consistency
                            # This handles old transactions before the fix
                            amount = debit_amount
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": line.description or line.journal_entry.description,
                                "debit": 0.0,
                                "credit": debit_amount,  # Show legacy debit as credit for display consistency
                                "amount": debit_amount,
                                "is_payment": True
                            })
                    elif line.journal_entry.source_type == "excess_contribution":
                        # Excess transferred to savings (debit on fund account)
                        debit_val = float(line.debit_amount) if line.debit_amount and line.debit_amount > 0 else 0.0
                        if debit_val > 0:
                            transactions.append({
                                "id": str(line.id),
                                "date": line.journal_entry.entry_date.isoformat(),
                                "description": "Overpayment transferred to Savings",
                                "debit": debit_val,
                                "credit": 0.0,
                                "amount": debit_val,
                                "is_excess_transfer": True
                            })
                    else:
                        # Treasurer corrections (splits, manual adjustments) on
                        # the admin fund account.
                        cred = float(line.credit_amount or 0)
                        deb = float(line.debit_amount or 0)
                        if cred == 0 and deb == 0:
                            continue
                        transactions.append({
                            "id": f"adj_{line.id}",
                            "date": line.journal_entry.entry_date.isoformat() if line.journal_entry.entry_date else None,
                            "description": line.description or line.journal_entry.description or "Treasurer adjustment",
                            "debit": deb,
                            "credit": cred,
                            "amount": cred if cred > 0 else deb,
                            "is_adjustment": True,
                            "source_type": line.journal_entry.source_type,
                        })

    except Exception as e:
        import logging
        import traceback
        logging.error(f"Error fetching {type} transactions: {str(e)}", exc_info=True)
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching {type} transactions: {str(e)}"
        )
    
    # Per-month loan + interest receivable balances drive the Loan Balance /
    # Interest Balance columns on the Statement page. Only meaningful for the
    # "savings" view today, but cheap to include for any type.
    monthly_loan_balances: list[dict] = []
    if type == "savings":
        try:
            monthly_loan_balances = get_member_monthly_loan_balances(db, member_profile.id)
        except Exception:
            monthly_loan_balances = []

    # Also expose the aggregate penalty-reversals list so the statement's
    # Contribution Summary can render each reversal inline as an audit
    # line. The Contribution Summary tiles themselves come from
    # `live_balances` below (record- and ledger-based), so the numbers
    # match what the member's Account Status card and Penalty Audit
    # modal display — a single source of truth across all three views.
    live_balances = None
    if type == "savings":
        try:
            from app.services.accounting import (
                get_member_savings_balance,
                get_member_social_fund_balance,
                get_member_admin_fund_balance,
                get_member_penalties_balance,
            )
            live_balances = {
                "savings": float(get_member_savings_balance(db, member_profile.id)),
                "social_fund": float(get_member_social_fund_balance(db, member_profile.id)),
                "admin_fund": float(get_member_admin_fund_balance(db, member_profile.id)),
                "penalties": float(get_member_penalties_balance(db, member_profile.id)),
            }
        except Exception:
            live_balances = None

    # Per-month itemization of live PenaltyRecord charges so the
    # statement can render "Penalty charges this month:" under each
    # declaration row. Bucketing uses date_issued (the day the fee hit
    # savings) so a fee auto-issued Jun 29 shows under June's row, and
    # separately the member's July declaration matches it via the
    # 1-month carry-back rule used elsewhere.
    penalty_charges_dto: list[dict] = []
    if type == "savings":
        try:
            from app.models.transaction import PenaltyRecord as _PRC, PenaltyRecordStatus as _PRCS
            live_pen_statuses = {
                _PRCS.APPROVED.value,
                _PRCS.PAID.value,
                _PRCS.REVERSAL_PENDING.value,
                _PRCS.PENDING.value,
            }
            _prs = (
                db.query(_PRC)
                .filter(_PRC.member_id == member_profile.id)
                .all()
            )
            for _pr in _prs:
                _sv = _pr.status.value if isinstance(_pr.status, _PRCS) else _pr.status
                if _sv not in live_pen_statuses:
                    continue
                if not _pr.date_issued:
                    continue
                _pt = _pr.penalty_type
                _fee = float(_pt.fee_amount) if _pt and _pt.fee_amount else 0.0
                if _fee <= 0:
                    continue
                _bucket = date(_pr.date_issued.year, _pr.date_issued.month, 1)
                penalty_charges_dto.append({
                    "id": str(_pr.id),
                    "penalty_type_name": (_pt.name if _pt else "Penalty"),
                    "fee_amount": _fee,
                    "date_issued": _pr.date_issued.isoformat(),
                    "effective_month": _bucket.isoformat(),
                    "notes": _pr.notes or "",
                    "status": _sv,
                })
        except Exception:
            penalty_charges_dto = []

    return {
        "type": type,
        "transactions": transactions,
        "monthly_loan_balances": monthly_loan_balances,
        "penalty_reversals": penalty_reversals_dto if type == "savings" else [],
        "penalty_charges": penalty_charges_dto,
        "live_balances": live_balances,
    }


@router.post("/deposits/upload")
def upload_deposit_proof(
    file: UploadFile = File(...),
    declaration_id: str = Form(...),
    amount: float = Form(...),
    reference: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload deposit proof of payment.
    
    When proof is uploaded:
    1. Declaration status changes from PENDING to APPROVED
    2. Deposit proof status is SUBMITTED
    3. Proof goes to Treasurer Dashboard for approval
    """
    from app.models.cycle import Cycle, CycleStatus
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")
    
    if member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Member account is not active")
    
    # Validate file type (PDF or image)
    allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.gif'}
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Get declaration
    try:
        declaration_uuid = UUID(declaration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid declaration ID format")
    
    declaration = db.query(Declaration).filter(Declaration.id == declaration_uuid).first()
    if not declaration:
        raise HTTPException(status_code=404, detail="Declaration not found")
    
    if declaration.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only upload proof for your own declarations")
    
    # A member can upload a fresh proof for any declaration in a state that
    # still needs one: PENDING (no proof yet) or REJECTED (treasurer asked
    # for revision). APPROVED declarations are immutable — the ledger has
    # already moved against them and the treasurer must reject first.
    if declaration.status not in (DeclarationStatus.PENDING, DeclarationStatus.REJECTED):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot upload proof — declaration status is "
                f"{declaration.status.value}. Ask the treasurer to reject it "
                "first if revisions are needed."
            ),
        )

    # If an existing proof is still pending or already approved, block — those
    # are "live" and would conflict with a new upload. If the only existing
    # proof was REJECTED, replace it (delete the stale file from disk, drop the
    # row) so the member can submit a corrected version. Re-uploading after a
    # rejection is the whole point.
    import os
    existing_live_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration_uuid,
        DepositProof.status.in_(
            [DepositProofStatus.SUBMITTED.value, DepositProofStatus.APPROVED.value]
        ),
    ).first()
    if existing_live_proof:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A {existing_live_proof.status} proof of payment already "
                "exists for this declaration. You can resubmit via the "
                "'View Proofs' tab only if the treasurer rejects the current one."
            ),
        )

    # Clean up any rejected proofs (file + row) so disk doesn't accumulate
    # redundant attachments. The audit trail of the rejection lives on the
    # declaration's status history, not the orphan file.
    rejected_proofs = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration_uuid,
        DepositProof.status == DepositProofStatus.REJECTED.value,
    ).all()
    for rp in rejected_proofs:
        if rp.upload_path:
            try:
                if os.path.isfile(rp.upload_path):
                    os.remove(rp.upload_path)
            except OSError:
                # If file removal fails (already gone, perms), keep going —
                # the DB cleanup is more important than the filesystem.
                pass
        db.delete(rp)
    if rejected_proofs:
        db.flush()
    
    # Get active cycle
    active_cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
    if not active_cycle:
        raise HTTPException(status_code=400, detail="No active cycle found")
    
    # Create upload directory
    DEPOSIT_PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ") if file.filename else "proof"
    file_path = DEPOSIT_PROOFS_DIR / f"deposit_{declaration_uuid}_{timestamp}_{safe_filename}"
    
    # Save file
    try:
        content = file.file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Create deposit proof record
    deposit_proof = DepositProof(
        member_id=member_profile.id,
        declaration_id=declaration_uuid,
        upload_path=str(file_path),
        amount=Decimal(str(amount)),
        reference=reference,
        cycle_id=active_cycle.id,
        status=DepositProofStatus.SUBMITTED.value
    )
    db.add(deposit_proof)
    db.flush()  # Flush to get deposit_proof.id
    
    # Update declaration status to PROOF (proof submitted, awaiting treasurer approval)
    declaration.status = DeclarationStatus.PROOF
    
    # Check if deposit is late and create automatic penalty record
    from app.models.cycle import CyclePhase, PhaseType
    from datetime import date as date_type
    
    deposits_phase = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == active_cycle.id,
        CyclePhase.phase_type == PhaseType.DEPOSITS
    ).first()
    
    if deposits_phase:
        auto_apply = getattr(deposits_phase, 'auto_apply_penalty', False)
        monthly_start_day = getattr(deposits_phase, 'monthly_start_day', None)
        monthly_end_day = getattr(deposits_phase, 'monthly_end_day', None)
        penalty_type_id = getattr(deposits_phase, 'penalty_type_id', None)
        
        if auto_apply and monthly_end_day and penalty_type_id:
            import calendar
            today = date_type.today()
            effective_date = declaration.effective_month
            is_late = False
            
            # Deposit period: monthly_start_day of effective month (e.g. 26th) to
            # monthly_end_day of NEXT month (e.g. 5th). Late if submitted after that end date.
            next_year = effective_date.year + (1 if effective_date.month == 12 else 0)
            next_month = (effective_date.month % 12) + 1
            _, last_day = calendar.monthrange(next_year, next_month)
            period_end_day = min(monthly_end_day, last_day)
            period_end = date_type(next_year, next_month, period_end_day)
            
            if today > period_end:
                is_late = True

            # Skip if the underlying declaration was created via treasurer
            # reconciliation — the treasurer entered the record on behalf
            # of the member for a past period; the deposit-window
            # deadline doesn't apply.
            if is_late:
                from app.services.transaction import is_reconciliation_declaration
                if is_reconciliation_declaration(db, declaration.id):
                    is_late = False

            if is_late:
                # Get penalty type
                from app.models.transaction import PenaltyType, PenaltyRecord, PenaltyRecordStatus
                penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                if penalty_type:
                    # Check if penalty record already exists for this deposit/declaration
                    existing_penalty = db.query(PenaltyRecord).filter(
                        PenaltyRecord.member_id == member_profile.id,
                        PenaltyRecord.penalty_type_id == penalty_type_id,
                        PenaltyRecord.notes.ilike(f"%Late Deposit%{effective_date.strftime('%B %Y')}%")
                    ).first()
                    
                    start_day = monthly_start_day if monthly_start_day is not None else 26
                    next_month_name = period_end.strftime("%B %Y")
                    effective_name = effective_date.strftime("%B %Y")
                    _ord = lambda n: str(n) + ("th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))
                    start_s = _ord(start_day)
                    end_s = _ord(monthly_end_day)
                    
                    if not existing_penalty:
                        # Get system user for system-generated penalties
                        from app.services.transaction import get_system_user_id, build_late_penalty_narration
                        system_user_id = get_system_user_id(db)
                        if not system_user_id:
                            # If no admin exists, skip penalty creation (shouldn't happen in production)
                            import logging
                            logging.warning(f"No admin user found to create system penalty for member {member_profile.id}")
                        else:
                            # Rich audit narration — captures the exact
                            # timestamp of the deposit proof upload.
                            _dep_period_start = None
                            if monthly_start_day is not None:
                                try:
                                    _dep_period_start = date_type(
                                        effective_date.year, effective_date.month, monthly_start_day,
                                    )
                                except Exception:
                                    _dep_period_start = None
                            _dep_offending_at = getattr(deposit_proof, "uploaded_at", None) or datetime.utcnow()
                            _narration = build_late_penalty_narration(
                                kind="Late Deposits",
                                effective_month=effective_date,
                                offending_at=_dep_offending_at,
                                period_start=_dep_period_start,
                                period_end=period_end,
                                monthly_start_day=monthly_start_day,
                                monthly_end_day=monthly_end_day,
                            )
                            # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                            late_penalty = PenaltyRecord(
                                member_id=member_profile.id,
                                penalty_type_id=penalty_type_id,
                                status=PenaltyRecordStatus.APPROVED.value,  # Use .value to ensure lowercase string is sent
                                created_by=system_user_id,  # Use admin user for system-generated penalties
                                notes=_narration,
                            )
                            db.add(late_penalty)
                            db.flush()
    
    db.commit()
    db.refresh(deposit_proof)
    
    return {
        "message": "Deposit proof uploaded successfully",
        "deposit_proof_id": str(deposit_proof.id),
        "declaration_status": declaration.status.value
    }


@router.get("/deposits")
def get_my_deposit_proofs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all deposit proofs for the current member."""
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return []
    
    # Hide 'superseded' proofs from the member — they're audit-only artefacts
    # produced when a reconciliation re-saves the same month. The treasurer/admin
    # views still see them.
    deposits = db.query(DepositProof).filter(
        DepositProof.member_id == member_profile.id,
        DepositProof.status != "superseded",
    ).order_by(DepositProof.uploaded_at.desc()).all()
    
    result = []
    for dep in deposits:
        # Get declaration details
        declaration = None
        if dep.declaration_id:
            declaration = db.query(Declaration).filter(Declaration.id == dep.declaration_id).first()
        
        result.append({
            "id": str(dep.id),
            "declaration_id": str(dep.declaration_id) if dep.declaration_id else None,
            "effective_month": declaration.effective_month.isoformat() if declaration and declaration.effective_month else None,
            "amount": float(dep.amount),
            "reference": dep.reference,
            "status": dep.status,
            "treasurer_comment": dep.treasurer_comment,
            "member_response": dep.member_response,
            "rejected_at": dep.rejected_at.isoformat() if dep.rejected_at else None,
            "uploaded_at": dep.uploaded_at.isoformat() if dep.uploaded_at else None,
            "upload_path": dep.upload_path
        })
    
    return result


@router.post("/deposits/{deposit_id}/respond")
def respond_to_deposit_proof_comment(
    deposit_id: str,
    response: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Member responds to treasurer's comment on deposit proof."""
    from uuid import UUID
    
    try:
        deposit_uuid = UUID(deposit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deposit ID format")
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")
    
    # Get deposit proof
    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_uuid).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    
    # Verify it belongs to the member
    if deposit.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only respond to your own deposit proofs")
    
    # Only allow response if proof is rejected
    if deposit.status != DepositProofStatus.REJECTED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot respond. Deposit proof status is {deposit.status}"
        )
    
    # Update member response
    deposit.member_response = response
    
    db.commit()
    db.refresh(deposit)
    
    return {
        "message": "Response submitted successfully",
        "deposit_id": str(deposit.id)
    }


@router.put("/deposits/{deposit_id}/attach-file")
def attach_deposit_proof_file(
    deposit_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach or replace the physical proof file on an existing DepositProof.

    Purpose: cover the case where the treasurer reconciled a member's
    declaration (declaration + deposit go straight to APPROVED with
    `upload_path = 'reconciliation'`, no file). The member later has the
    paper trail and wants to attach it — **without** requiring the
    treasurer to re-approve the deposit.

    This endpoint:
      * Overwrites `deposit.upload_path` with the newly-saved file path.
      * Does NOT change `deposit.status` — the deposit stays approved (or
        whatever it currently is).
      * Does NOT touch the linked Declaration's status.
      * Does NOT touch the ledger.
      * Cleans up the old physical file when present (the "reconciliation"
        sentinel is treated as no-file). Best-effort — if unlink fails the
        DB path still gets replaced.

    Refused when:
      * The deposit belongs to someone else.
      * The deposit is REJECTED — that flow has its own resubmit path
        (`PUT /deposits/{id}/resubmit`) which changes status and needs
        treasurer re-approval.
    """
    import os
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")
    if member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Member account is not active")

    try:
        deposit_uuid = UUID(deposit_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid deposit_id")

    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_uuid).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    if deposit.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only attach files to your own deposit proofs")

    if deposit.status == DepositProofStatus.REJECTED.value:
        raise HTTPException(
            status_code=400,
            detail=(
                "This deposit was rejected — use the Resubmit action instead so the "
                "treasurer can review your revised proof."
            ),
        )

    # Validate file type (same allowlist as the primary upload endpoint).
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".gif"}
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    # Save the new file — same naming pattern as `POST /deposits/upload`
    # so the treasurer's existing file-serving endpoint works unchanged.
    DEPOSIT_PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = (
        "".join(c for c in file.filename if c.isalnum() or c in "._- ")
        if file.filename else "proof"
    )
    declaration_stub = str(deposit.declaration_id or deposit.id)
    file_path = DEPOSIT_PROOFS_DIR / f"deposit_{declaration_stub}_{timestamp}_{safe_filename}"
    try:
        content = file.file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Best-effort cleanup of the previous physical file. "reconciliation" is
    # a sentinel, not a filename, so we skip unlinking in that case.
    was_reconciliation = deposit.upload_path == "reconciliation"
    old_path = deposit.upload_path
    if old_path and old_path != "reconciliation":
        try:
            if os.path.isfile(old_path):
                os.remove(old_path)
        except OSError:
            pass

    deposit.upload_path = str(file_path)
    db.commit()
    db.refresh(deposit)

    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "member",
        action="Deposit proof file attached" if was_reconciliation else "Deposit proof file replaced",
        details=(
            f"deposit={deposit_id} status={deposit.status} "
            f"new_file={file_path.name if hasattr(file_path, 'name') else file_path}"
        ),
    )
    return {
        "message": (
            "Proof file attached." if was_reconciliation else "Proof file replaced."
        ),
        "deposit_id": str(deposit.id),
        "upload_path": deposit.upload_path,
        "status": deposit.status,
    }


@router.put("/deposits/{deposit_id}/resubmit")
def resubmit_deposit_proof(
    deposit_id: str,
    file: Optional[UploadFile] = File(None),
    amount: Optional[float] = Form(None),
    reference: Optional[str] = Form(None),
    member_response: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Resubmit a rejected deposit proof.
    
    Allows updating a REJECTED deposit proof with optional:
    - New file (if provided, replaces old file)
    - Updated amount (must match declaration total)
    - Updated reference
    - Member response/comment
    
    Changes deposit proof status from REJECTED to SUBMITTED
    and declaration status from PENDING to PROOF.
    """
    from uuid import UUID
    from app.models.cycle import Cycle, CycleStatus
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        deposit_uuid = UUID(deposit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deposit ID format")
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        raise HTTPException(status_code=403, detail="Member profile not found")
    
    if member_profile.status != MemberStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Member account is not active")
    
    # Get deposit proof
    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_uuid).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    
    # Verify it belongs to the member
    if deposit.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="You can only resubmit your own deposit proofs")
    
    # Only allow resubmission if proof is rejected
    if deposit.status != DepositProofStatus.REJECTED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resubmit. Deposit proof status is {deposit.status}. Only rejected proofs can be resubmitted."
        )
    
    # Get associated declaration
    if not deposit.declaration_id:
        raise HTTPException(
            status_code=400,
            detail="Deposit proof is not associated with a declaration"
        )
    
    declaration = db.query(Declaration).filter(Declaration.id == deposit.declaration_id).first()
    if not declaration:
        raise HTTPException(status_code=404, detail="Associated declaration not found")
    
    # Verify declaration belongs to member
    if declaration.member_id != member_profile.id:
        raise HTTPException(status_code=403, detail="Declaration does not belong to you")
    
    # Declaration must be in PENDING status to allow resubmission
    if declaration.status != DeclarationStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resubmit. Declaration status is {declaration.status.value}. Declaration must be PENDING to resubmit proof."
        )
    
    # Handle file upload if provided
    old_file_path = None
    if file and file.filename:
        # Validate file type
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.gif'}
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Store old file path for deletion
        old_file_path = Path(deposit.upload_path) if deposit.upload_path else None
        
        # Create upload directory
        DEPOSIT_PROOFS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ") if file.filename else "proof"
        new_file_path = DEPOSIT_PROOFS_DIR / f"deposit_{deposit.declaration_id}_{timestamp}_{safe_filename}"
        
        # Save new file
        try:
            content = file.file.read()
            with open(new_file_path, "wb") as f:
                f.write(content)
            deposit.upload_path = str(new_file_path)
            logger.info(f"New deposit proof file saved: {new_file_path}")
        except Exception as e:
            logger.error(f"Failed to save new deposit proof file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
        # Delete old file if it exists
        if old_file_path and old_file_path.exists():
            try:
                old_file_path.unlink()
                logger.info(f"Old deposit proof file deleted: {old_file_path}")
            except Exception as e:
                # Log warning but don't fail - old file deletion is non-critical
                logger.warning(f"Failed to delete old deposit proof file {old_file_path}: {str(e)}")
    
    # Handle amount update if provided
    if amount is not None:
        # Calculate declaration total
        declaration_total = Decimal("0.00")
        if declaration.declared_savings_amount:
            declaration_total += declaration.declared_savings_amount
        if declaration.declared_social_fund:
            declaration_total += declaration.declared_social_fund
        if declaration.declared_admin_fund:
            declaration_total += declaration.declared_admin_fund
        if declaration.declared_penalties:
            declaration_total += declaration.declared_penalties
        if declaration.declared_interest_on_loan:
            declaration_total += declaration.declared_interest_on_loan
        if declaration.declared_loan_repayment:
            declaration_total += declaration.declared_loan_repayment
        
        deposit_amount = Decimal(str(amount))
        
        # Validate amount matches declaration total (with small tolerance for rounding)
        if abs(deposit_amount - declaration_total) > Decimal("0.01"):
            raise HTTPException(
                status_code=400,
                detail=f"Deposit amount ({deposit_amount}) does not match declaration total ({declaration_total}). "
                       f"Difference: {abs(deposit_amount - declaration_total)}"
            )
        
        deposit.amount = deposit_amount
    
    # Update reference if provided
    if reference is not None:
        deposit.reference = reference
    
    # Update member response if provided
    if member_response is not None:
        deposit.member_response = member_response
    
    # Update deposit proof status to SUBMITTED
    deposit.status = DepositProofStatus.SUBMITTED.value
    
    # Update declaration status to PROOF (proof resubmitted, awaiting treasurer approval)
    declaration.status = DeclarationStatus.PROOF
    
    # Note: We keep rejected_at and rejected_by for audit trail
    # They show the history of the rejection even after resubmission
    
    db.commit()
    db.refresh(deposit)
    db.refresh(declaration)
    
    logger.info(f"Deposit proof {deposit.id} resubmitted successfully. Declaration {declaration.id} status updated to PROOF.")
    
    return {
        "message": "Deposit proof resubmitted successfully",
        "deposit_proof_id": str(deposit.id),
        "declaration_status": declaration.status.value
    }


# ---------------------------------------------------------------------------
# Group Summary Report
# ---------------------------------------------------------------------------

@router.get("/reports/group-summary")
def get_group_summary_report(
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Monthly group financial summary: savings, loans, deposits and proportional profit share."""
    from sqlalchemy import extract, func as sqlfunc
    from app.models.ledger import LedgerAccount, JournalEntry, JournalLine
    from app.models.user import UserRoleEnum
    from app.models.cycle import Cycle, CycleStatus

    # ── parse month ──────────────────────────────────────────────────────────
    if month:
        try:
            target_date = datetime.strptime(month, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")
    else:
        today = date.today()
        target_date = date(today.year, today.month, 1)

    month_start = datetime.combine(target_date, datetime.min.time())
    if target_date.month == 12:
        next_month_date = date(target_date.year + 1, 1, 1)
    else:
        next_month_date = date(target_date.year, target_date.month + 1, 1)
    month_end = datetime.combine(next_month_date, datetime.min.time())

    # ── members ──────────────────────────────────────────────────────────────
    members_users = (
        db.query(MemberProfile, User)
        .join(User, MemberProfile.user_id == User.id)
        .filter(MemberProfile.status == MemberStatus.ACTIVE)
        .all()
    )
    members_users = [
        (m, u) for m, u in members_users
        if u.role not in (UserRoleEnum.ADMIN,) and (u.first_name or u.last_name)
    ]
    member_ids = [m.id for m, _ in members_users]

    # ── batch-fetch ledger accounts ───────────────────────────────────────────
    def _accounts_by_member(keyword: str) -> dict:
        return {
            a.member_id: a
            for a in db.query(LedgerAccount).filter(
                LedgerAccount.member_id.in_(member_ids),
                LedgerAccount.account_name.ilike(f"%{keyword}%")
            ).all()
        }

    savings_accs = _accounts_by_member("savings")
    social_accs  = _accounts_by_member("social fund")
    admin_accs   = _accounts_by_member("admin fund")

    # ── helper: net balance per account_id (credits − debits) over a window ──
    # Source-type-agnostic so excess transfers, treasurer splits and any other
    # legitimate adjustments to a member's savings flow into the totals. The
    # date filter is on the reporting bucket (dealing_month) rather than the
    # raw entry_date so a deposit approved in June but declared for May lands
    # in May's BF for June's report (matches the Statement view).
    def _net_balance(acc_ids: list,
                     dealing_lt: date = None,
                     dealing_ge: date = None,
                     dealing_lt_strict: date = None) -> dict:
        if not acc_ids:
            return {}
        q_cr = (
            db.query(JournalLine.ledger_account_id, sqlfunc.sum(JournalLine.credit_amount))
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .filter(
                JournalLine.ledger_account_id.in_(acc_ids),
                JournalEntry.reversed_by.is_(None),
            )
        )
        q_dr = (
            db.query(JournalLine.ledger_account_id, sqlfunc.sum(JournalLine.debit_amount))
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .filter(
                JournalLine.ledger_account_id.in_(acc_ids),
                JournalEntry.reversed_by.is_(None),
            )
        )
        if dealing_lt is not None:
            q_cr = q_cr.filter(JournalEntry.dealing_month < dealing_lt)
            q_dr = q_dr.filter(JournalEntry.dealing_month < dealing_lt)
        if dealing_ge is not None:
            q_cr = q_cr.filter(JournalEntry.dealing_month >= dealing_ge)
            q_dr = q_dr.filter(JournalEntry.dealing_month >= dealing_ge)
        if dealing_lt_strict is not None:
            q_cr = q_cr.filter(JournalEntry.dealing_month < dealing_lt_strict)
            q_dr = q_dr.filter(JournalEntry.dealing_month < dealing_lt_strict)
        credits = {str(a): float(v or 0) for a, v in q_cr.group_by(JournalLine.ledger_account_id).all()}
        debits  = {str(a): float(v or 0) for a, v in q_dr.group_by(JournalLine.ledger_account_id).all()}
        return {a: credits.get(a, 0.0) - debits.get(a, 0.0) for a in {*credits, *debits}}

    def _member_val(accs: dict, amounts: dict, member_id) -> float:
        acc = accs.get(member_id)
        return amounts.get(str(acc.id), 0.0) if acc else 0.0

    sav_ids    = [a.id for a in savings_accs.values()]
    social_ids = [a.id for a in social_accs.values()]
    admin_ids  = [a.id for a in admin_accs.values()]

    # BF = net balance with dealing_month strictly before target month start
    sav_bf_map    = _net_balance(sav_ids,    dealing_lt=target_date)
    social_bf_map = _net_balance(social_ids, dealing_lt=target_date)
    admin_bf_map  = _net_balance(admin_ids,  dealing_lt=target_date)
    # This-month delta (used for the interest-share weighting)
    sav_month_map = _net_balance(sav_ids, dealing_ge=target_date, dealing_lt_strict=next_month_date)

    total_savings_bf = sum(_member_val(savings_accs, sav_bf_map, m.id) for m, _ in members_users)

    # ── declarations for this month (any status → savings_declared display) ──
    declarations = {
        str(d.member_id): d
        for d in db.query(Declaration).filter(
            Declaration.member_id.in_(member_ids),
            extract('year',  Declaration.effective_month) == target_date.year,
            extract('month', Declaration.effective_month) == target_date.month
        ).all()
    }

    # ── approved declarations this month (for per-member repayment amounts) ──
    approved_decls_month = db.query(Declaration).filter(
        Declaration.member_id.in_(member_ids),
        Declaration.status == DeclarationStatus.APPROVED,
        extract('year',  Declaration.effective_month) == target_date.year,
        extract('month', Declaration.effective_month) == target_date.month
    ).all()
    approved_decl_month_by_member = {str(d.member_id): d for d in approved_decls_month}

    # ── approved declarations before this month (for loan_bf) ────────────────
    approved_decls_prior = db.query(Declaration).filter(
        Declaration.member_id.in_(member_ids),
        Declaration.status == DeclarationStatus.APPROVED,
        Declaration.effective_month < target_date
    ).all()
    prior_repayments_by_member: dict = {}
    for d in approved_decls_prior:
        mid_str = str(d.member_id)
        prior_repayments_by_member[mid_str] = (
            prior_repayments_by_member.get(mid_str, 0.0) + float(d.declared_loan_repayment or 0)
        )

    # ── loans ─────────────────────────────────────────────────────────────────
    all_loans: dict = {}
    for loan in db.query(Loan).filter(Loan.member_id.in_(member_ids)).all():
        all_loans.setdefault(str(loan.member_id), []).append(loan)

    # ── interest income: accrues monthly from all active outstanding loans ────
    # When a loan is issued the monthly interest (amount × rate%) is the group's
    # income pool. It accrues every month the loan remains outstanding.
    total_interest_month = float(
        db.query(sqlfunc.sum(Loan.loan_amount * Loan.percentage_interest / 100))
        .filter(
            Loan.disbursement_date < next_month_date,
            Loan.disbursement_date.isnot(None),
            Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED])
        )
        .scalar() or 0
    )
    # BF = monthly interest from all loans that were disbursed before this month
    # (regardless of current status — they generated income while active)
    total_interest_bf = float(
        db.query(sqlfunc.sum(Loan.loan_amount * Loan.percentage_interest / 100))
        .filter(
            Loan.disbursement_date < target_date,
            Loan.disbursement_date.isnot(None)
        )
        .scalar() or 0
    )
    # Total approved deposits this month — the distribution denominator
    total_group_deposited = sum(_member_val(savings_accs, sav_month_map, m.id) for m, _ in members_users)

    # ── penalties approved this month ─────────────────────────────────────────
    penalty_types_map = {str(pt.id): pt for pt in db.query(PenaltyType).all()}
    penalties_month: dict = {}
    for p in db.query(PenaltyRecord).filter(
        PenaltyRecord.member_id.in_(member_ids),
        PenaltyRecord.status == PenaltyRecordStatus.APPROVED,
        PenaltyRecord.approved_at >= month_start,
        PenaltyRecord.approved_at < month_end
    ).all():
        penalties_month.setdefault(str(p.member_id), []).append(p)

    # ── build rows ────────────────────────────────────────────────────────────
    rows = []
    for member, user in members_users:
        mid  = str(member.id)
        name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip()

        savings_bf      = _member_val(savings_accs, sav_bf_map,    member.id)
        social_fund_bf  = _member_val(social_accs, social_bf_map, member.id)
        admin_fund_bf   = _member_val(admin_accs,  admin_bf_map,  member.id)

        interest_bf = round((savings_bf / total_savings_bf) * total_interest_bf, 2) \
            if total_savings_bf > 0 else 0.0

        loan_amount_total = sum(float(l.loan_amount) for l in all_loans.get(mid, []))
        loan_bf = max(0.0, loan_amount_total - prior_repayments_by_member.get(mid, 0.0))

        decl = declarations.get(mid)
        savings_declared      = float(decl.declared_savings_amount or 0) if decl else 0.0
        social_fund_declared  = float(decl.declared_social_fund or 0) if decl else 0.0
        admin_fund_declared   = float(decl.declared_admin_fund  or 0) if decl else 0.0

        penalty_total = sum(
            float(penalty_types_map[str(p.penalty_type_id)].fee_amount)
            for p in penalties_month.get(mid, [])
            if str(p.penalty_type_id) in penalty_types_map
        )

        approved_decl = approved_decl_month_by_member.get(mid)
        repayment_principal = float(approved_decl.declared_loan_repayment or 0) if approved_decl else 0.0
        repayment_interest  = float(approved_decl.declared_interest_on_loan or 0) if approved_decl else 0.0

        # Declaration Amount = sum of all declared components for the month
        # (Savings + Social Fund + Admin Fund + Penalty + Interest paid + Loan Repayment)
        total_deposited = (
            savings_declared
            + social_fund_declared
            + admin_fund_declared
            + penalty_total
            + repayment_principal
            + repayment_interest
        )

        # Interest earned = member's share of this month's loan interest income,
        # weighted by their savings deposit for the month (not the full declaration)
        savings_deposited = _member_val(savings_accs, sav_month_map, member.id)
        interest_earned = round((savings_deposited / total_group_deposited) * total_interest_month, 2) \
            if total_group_deposited > 0 else 0.0

        loan_applied = interest_on_loan_applied = 0.0
        for loan in all_loans.get(mid, []):
            if loan.disbursement_date and target_date <= loan.disbursement_date < next_month_date:
                loan_applied             += float(loan.loan_amount)
                interest_on_loan_applied += float(loan.loan_amount) * float(loan.percentage_interest) / 100

        rows.append({
            "member_id":                str(member.id),
            "name":                     name,
            "savings_bf":               round(savings_bf, 2),
            "social_fund_bf":           round(social_fund_bf, 2),
            "admin_fund_bf":            round(admin_fund_bf, 2),
            "interest_bf":              round(interest_bf, 2),
            "loan_bf":                  round(loan_bf, 2),
            "savings_declared":         round(savings_declared, 2),
            "social_fund_declared":     round(social_fund_declared, 2),
            "admin_fund_declared":      round(admin_fund_declared, 2),
            "penalty":                  round(penalty_total, 2),
            "loan_repayment":           round(repayment_principal, 2),
            "interest_on_loan_paid":    round(repayment_interest, 2),
            "total_deposited":          round(total_deposited, 2),
            "interest_earned":          round(interest_earned, 2),
            "loan_applied":             round(loan_applied, 2),
            "interest_on_loan_applied": round(interest_on_loan_applied, 2),
        })

    rows.sort(key=lambda x: (x["name"].rsplit(" ", 1)[-1].lower(), x["name"].rsplit(" ", 1)[0].lower()))

    num_keys = [
        "savings_bf", "social_fund_bf", "admin_fund_bf", "interest_bf", "loan_bf",
        "savings_declared", "social_fund_declared", "admin_fund_declared", "penalty",
        "loan_repayment", "interest_on_loan_paid", "total_deposited",
        "interest_earned", "loan_applied", "interest_on_loan_applied",
    ]
    totals = {k: round(sum(r[k] for r in rows), 2) for k in num_keys}
    totals["name"] = "TOTAL"

    return {"month": target_date.isoformat(), "members": rows, "totals": totals}


# ---------------------------------------------------------------------------
# Member Savings History (for group-report drill-down)
# ---------------------------------------------------------------------------

@router.get("/reports/member-savings-history")
def get_member_savings_history(
    member_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get savings transaction history for a specific member (used by group report drill-down)."""
    from app.models.ledger import LedgerAccount, JournalEntry, JournalLine
    from app.models.transaction import Declaration, DeclarationStatus, DepositProof, DepositApproval
    from app.models.member import MemberProfile
    import uuid as _uuid

    try:
        member_uuid = _uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid member_id format")

    member_profile = db.query(MemberProfile).filter(MemberProfile.id == member_uuid).first()
    if not member_profile:
        raise HTTPException(status_code=404, detail="Member not found")

    member_name = f"{member_profile.user.first_name or ''} {member_profile.user.last_name or ''}".strip()

    transactions = []

    # Approved deposits
    deposit_approvals = db.query(DepositApproval).join(
        DepositProof, DepositApproval.deposit_proof_id == DepositProof.id
    ).join(
        JournalEntry, DepositApproval.journal_entry_id == JournalEntry.id
    ).filter(
        DepositProof.member_id == member_profile.id,
        JournalEntry.reversed_by.is_(None)
    ).order_by(JournalEntry.entry_date.desc()).all()

    for da in deposit_approvals:
        deposit = da.deposit_proof
        declaration = deposit.declaration if deposit else None

        if declaration:
            date_str = declaration.effective_month.isoformat()
            description = f"Deposit approved for {declaration.effective_month.strftime('%B %Y')} declaration"
        else:
            date_str = da.journal_entry.entry_date.isoformat()
            description = "Approved deposit"

        transactions.append({
            "id": str(da.id),
            "date": date_str,
            "description": description,
            "debit": 0.0,
            "credit": float(deposit.amount),
            "amount": float(deposit.amount)
        })

    # Declarations as debit entries — include any with ANY declared component,
    # not just savings, so penalty-only / interest-only / loan-repayment-only
    # declarations show up too.
    from sqlalchemy import or_ as _or_
    declarations = db.query(Declaration).filter(
        Declaration.member_id == member_profile.id,
        _or_(
            Declaration.declared_savings_amount > 0,
            Declaration.declared_social_fund > 0,
            Declaration.declared_admin_fund > 0,
            Declaration.declared_penalties > 0,
            Declaration.declared_loan_repayment > 0,
            Declaration.declared_interest_on_loan > 0,
        ),
    ).order_by(Declaration.created_at.desc()).all()

    from app.services.accounting import compute_posted_breakdown as _posted_bd
    from app.services.accounting import get_reconciliation_notes as _recon_notes
    for declaration in declarations:
        posted_items = _posted_bd(
            db, member_profile.id,
            declaration.effective_month.year,
            declaration.effective_month.month,
        )
        declared_check = {
            "savings": float(declaration.declared_savings_amount or 0),
            "social_fund": float(declaration.declared_social_fund or 0),
            "admin_fund": float(declaration.declared_admin_fund or 0),
            "penalty": float(declaration.declared_penalties or 0),
        }
        has_reconciliation_discrepancy = (
            declaration.status == DeclarationStatus.APPROVED
            and any(abs(posted_items[k] - declared_check[k]) > 0.01 for k in declared_check)
        )
        reconciliation_notes = (
            _recon_notes(
                db, member_profile.id,
                declaration.effective_month.year,
                declaration.effective_month.month,
            )
            if has_reconciliation_discrepancy
            else []
        )
        transactions.append({
            "id": f"declaration_{declaration.id}",
            "date": declaration.effective_month.isoformat(),
            "description": f"Declaration for {declaration.effective_month.strftime('%B %Y')}",
            "debit": float(declaration.declared_savings_amount or 0),
            "credit": 0.0,
            "amount": float(declaration.declared_savings_amount or 0),
            "is_declaration": True,
            "declaration_items": {
                "savings_amount":   float(declaration.declared_savings_amount or 0),
                "social_fund":      float(declaration.declared_social_fund or 0),
                "admin_fund":       float(declaration.declared_admin_fund or 0),
                "penalties":        float(declaration.declared_penalties or 0),
                "loan_repayment":   float(declaration.declared_loan_repayment or 0),
                "interest_on_loan": float(declaration.declared_interest_on_loan or 0),
            },
            "posted_items": posted_items,
            "has_reconciliation_discrepancy": has_reconciliation_discrepancy,
            "reconciliation_notes": reconciliation_notes,
        })

    # NOTE: excess_contribution / transaction_split / transaction_reverse JEs are
    # intentionally NOT surfaced as separate rows — they're internal
    # reclassifications of money already counted under the originating
    # deposit. Surfacing them would inflate the "Approved Deposit" column.
    # Their effect on category balances is reflected via the posted_items
    # annotation on the declaration row.

    transactions.sort(key=lambda x: x["date"], reverse=True)

    try:
        monthly_loan_balances = get_member_monthly_loan_balances(db, member_profile.id)
    except Exception:
        monthly_loan_balances = []

    return {
        "member_name": member_name,
        "member_id": member_id,
        "type": "savings",
        "transactions": transactions,
        "monthly_loan_balances": monthly_loan_balances,
    }
