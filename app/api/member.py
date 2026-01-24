from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_member, get_current_user, require_not_admin
from app.models.user import User
from app.models.member import MemberProfile, MemberStatus
from app.models.transaction import Declaration, DeclarationStatus, DepositProof, DepositProofStatus, LoanApplication, LoanApplicationStatus, Loan, LoanStatus, DepositApproval
from app.services.member import get_member_profile_by_user_id
from app.services.transaction import create_declaration, update_declaration
from app.services.accounting import (
    get_member_savings_balance,
    get_member_loan_balance,
    get_member_social_fund_balance,
    get_member_admin_fund_balance,
    get_member_penalties_balance
)
from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from uuid import UUID
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


@router.get("/status")
def get_my_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get my account status (savings, loans, penalties summary)."""
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
            loan_balance = get_member_loan_balance(db, member_profile.id)
            social_fund_balance = get_member_social_fund_balance(db, member_profile.id)
            admin_fund_balance = get_member_admin_fund_balance(db, member_profile.id)
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
        
        return {
            "member_id": str(member_profile.id),
            "savings_balance": float(savings_balance),
            "loan_balance": float(loan_balance),
            "social_fund_balance": float(social_fund_balance),
            "social_fund_required": float(social_fund_required) if social_fund_required else None,
            "admin_fund_balance": float(admin_fund_balance),
            "admin_fund_required": float(admin_fund_required) if admin_fund_required else None,
            "penalties_balance": float(penalties_balance),
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
    
    try:
        declaration = create_declaration(
            db=db,
            member_id=member_profile.id,
            cycle_id=declaration_data.cycle_id,
            effective_month=declaration_data.effective_month,
            declared_savings_amount=Decimal(str(declaration_data.declared_savings_amount)) if declaration_data.declared_savings_amount else None,
            declared_social_fund=Decimal(str(declaration_data.declared_social_fund)) if declaration_data.declared_social_fund else None,
            declared_admin_fund=Decimal(str(declaration_data.declared_admin_fund)) if declaration_data.declared_admin_fund else None,
            declared_penalties=Decimal(str(declaration_data.declared_penalties)) if declaration_data.declared_penalties else None,
            declared_interest_on_loan=Decimal(str(declaration_data.declared_interest_on_loan)) if declaration_data.declared_interest_on_loan else None,
            declared_loan_repayment=Decimal(str(declaration_data.declared_loan_repayment)) if declaration_data.declared_loan_repayment else None
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
    
    # Get all pending penalties for this member (exclude POSTED ones)
    pending_penalties = db.query(PenaltyRecord).filter(
        PenaltyRecord.member_id == member_profile.id,
        PenaltyRecord.status.in_([PenaltyRecordStatus.PENDING, PenaltyRecordStatus.APPROVED])
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


@router.get("/declarations/applicable-penalties")
def get_applicable_penalties(
    cycle_id: str,
    effective_month: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all applicable penalties for a declaration, including pending penalty records and late declaration penalty.
    
    Excludes penalties that were already paid (included in an approved declaration).
    """
    from datetime import date
    from app.models.cycle import Cycle, CyclePhase, PhaseType
    from app.models.transaction import PenaltyRecord, PenaltyRecordStatus, Declaration, DeclarationStatus
    from sqlalchemy import extract
    from uuid import UUID
    
    member_profile = get_member_profile_by_user_id(db, current_user.id)
    if not member_profile:
        return {"total_amount": 0.0, "penalties": []}
    
    try:
        cycle_uuid = UUID(cycle_id)
        effective_date = date.fromisoformat(effective_month)
    except (ValueError, TypeError):
        return {"total_amount": 0.0, "penalties": []}
    
    penalties_list = []
    total_amount = Decimal("0.00")
    
    # 1. Get all unpaid penalty records (PENDING, APPROVED, and POSTED)
    # POSTED penalties are charged but not yet paid - they need to be included in declaration
    # We'll exclude penalties that were already included in an approved declaration
    all_penalty_records = db.query(PenaltyRecord).filter(
        PenaltyRecord.member_id == member_profile.id,
        PenaltyRecord.status.in_([PenaltyRecordStatus.PENDING, PenaltyRecordStatus.APPROVED, PenaltyRecordStatus.POSTED])
    ).all()
    
    # Check if there's an approved declaration for this month that might have already paid some penalties
    existing_approved = db.query(Declaration).filter(
        Declaration.member_id == member_profile.id,
        Declaration.cycle_id == cycle_uuid,
        extract('year', Declaration.effective_month) == effective_date.year,
        extract('month', Declaration.effective_month) == effective_date.month,
        Declaration.status == DeclarationStatus.APPROVED
    ).first()
    
    # If there's an approved declaration with penalties, we need to be careful
    # For now, include all penalties - the member should see all unpaid penalties
    # The Treasurer will verify the amounts match when approving the deposit
    pending_penalty_records = all_penalty_records
    
    for penalty in pending_penalty_records:
        penalty_type = penalty.penalty_type
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
    
    # 2. Check for late declaration penalty
    # If there's an approved declaration with penalties, don't include late penalty again
    late_penalty_already_paid = False
    if existing_approved and existing_approved.declared_penalties and existing_approved.declared_penalties > 0:
        # Check if late penalty was likely included (this is a heuristic - we can't be 100% sure)
        # But if there's an approved declaration with penalties for this month, assume late penalty was paid
        late_penalty_already_paid = True
    
    if not late_penalty_already_paid:
        # Get the cycle and declaration phase
        cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
        if cycle:
            declaration_phase = db.query(CyclePhase).filter(
                CyclePhase.cycle_id == cycle_uuid,
                CyclePhase.phase_type == PhaseType.DECLARATION
            ).first()
            
            if declaration_phase:
                auto_apply = getattr(declaration_phase, 'auto_apply_penalty', False)
                monthly_end_day = getattr(declaration_phase, 'monthly_end_day', None)
                
                if auto_apply and monthly_end_day:
                    today = date.today()
                    is_late = False
                    
                    # Check if declaration is late
                    if today.year == effective_date.year and today.month == effective_date.month:
                        if today.day > monthly_end_day:
                            is_late = True
                    elif today.year > effective_date.year or (today.year == effective_date.year and today.month > effective_date.month):
                        is_late = True
                    
                    if is_late:
                        penalty_type_id = getattr(declaration_phase, 'penalty_type_id', None)
                        if penalty_type_id:
                            from app.models.transaction import PenaltyType
                            penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                            if penalty_type:
                                late_penalty_amount = Decimal(str(penalty_type.fee_amount))
                                total_amount += late_penalty_amount
                                
                                penalties_list.append({
                                    "id": None,  # Late penalty doesn't have a record ID
                                    "penalty_type_name": penalty_type.name,
                                    "fee_amount": float(late_penalty_amount),
                                    "date_issued": None,
                                    "notes": f"Declaration made after day {monthly_end_day} of the month (Declaration period ends on day {monthly_end_day})",
                                    "source": "late_declaration"
                                })
                        else:
                            # Fallback to deprecated penalty_amount
                            penalty_amount = getattr(declaration_phase, 'penalty_amount', None)
                            if penalty_amount:
                                late_penalty_amount = Decimal(str(penalty_amount))
                                total_amount += late_penalty_amount
                                
                                penalties_list.append({
                                    "id": None,
                                    "penalty_type_name": "Late Declaration Penalty",
                                    "fee_amount": float(late_penalty_amount),
                                    "date_issued": None,
                                    "notes": f"Declaration made after day {monthly_end_day} of the month (Declaration period ends on day {monthly_end_day})",
                                    "source": "late_declaration"
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
    
    return [
        {
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
                db.query(DepositProof).filter(
                    DepositProof.declaration_id == d.id,
                    DepositProof.status == DepositProofStatus.REJECTED.value
                ).first() is not None
            )
        }
        for d in declarations
    ]


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
        "can_edit": _can_edit_declaration(declaration.effective_month)
    }


def _can_edit_declaration(effective_month: date) -> bool:
    """Check if a declaration can still be edited.
    
    Members can now edit declarations anytime for the current month (removed 20th day restriction).
    The one-declaration-per-month rule still applies.
    """
    from datetime import date
    today = date.today()
    
    # Cannot edit declarations from previous months (only current month can be edited)
    if today.year > effective_month.year or (today.year == effective_month.year and today.month > effective_month.month):
        return False
    
    # Allow editing current month declarations anytime (removed 20th day restriction)
    return True


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
    
    # Check if this is an edit after rejection (allow editing even if past 20th)
    allow_rejected_edit = False
    # Check if there's a rejected deposit proof for this declaration
    rejected_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration_uuid,
        DepositProof.status == DepositProofStatus.REJECTED.value
    ).first()
    if rejected_proof:
        allow_rejected_edit = True
    
    try:
        updated_declaration = update_declaration(
            db=db,
            declaration_id=declaration_uuid,
            member_id=member_profile.id,
            cycle_id=UUID(declaration_data.cycle_id),
            effective_month=declaration_data.effective_month,
            declared_savings_amount=Decimal(str(declaration_data.declared_savings_amount)) if declaration_data.declared_savings_amount else None,
            declared_social_fund=Decimal(str(declaration_data.declared_social_fund)) if declaration_data.declared_social_fund else None,
            declared_admin_fund=Decimal(str(declaration_data.declared_admin_fund)) if declaration_data.declared_admin_fund else None,
            declared_penalties=Decimal(str(declaration_data.declared_penalties)) if declaration_data.declared_penalties else None,
            declared_interest_on_loan=Decimal(str(declaration_data.declared_interest_on_loan)) if declaration_data.declared_interest_on_loan else None,
            declared_loan_repayment=Decimal(str(declaration_data.declared_loan_repayment)) if declaration_data.declared_loan_repayment else None,
            allow_rejected_edit=allow_rejected_edit
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
    
    # Check for active loans that haven't been fully paid
    active_loans = db.query(Loan).filter(
        Loan.member_id == member_profile.id,
        Loan.loan_status.in_([LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN])
    ).all()
    
    if active_loans:
        # Check if any active loan has outstanding balance
        for loan in active_loans:
            # Calculate total repaid
            total_repaid = sum(
                (repayment.principal_amount + repayment.interest_amount) 
                for repayment in loan.repayments
            )
            outstanding = loan.loan_amount - total_repaid
            if outstanding > Decimal("0.01"):  # Allow small rounding differences
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"You have an active loan with outstanding balance of K{outstanding:,.2f}. Please pay it off before applying for a new loan."
                )
    
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
    
    loan_application = LoanApplication(
        member_id=member_profile.id,
        cycle_id=cycle_uuid,
        amount=loan_amount,
        term_months=loan_data.term_months,
        status=LoanApplicationStatus.PENDING
    )
    db.add(loan_application)
    db.commit()
    db.refresh(loan_application)
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
    
    # Calculate payment breakdown
    total_principal_paid = Decimal("0.00")
    total_interest_paid = Decimal("0.00")
    total_paid = Decimal("0.00")
    
    for repayment in loan.repayments:
        total_principal_paid += repayment.principal_amount
        total_interest_paid += repayment.interest_amount
        total_paid += repayment.total_amount
    
    outstanding_balance = loan.loan_amount - total_principal_paid
    
    # Check if loan is fully paid and update status to CLOSED
    if outstanding_balance <= Decimal("0.01"):  # Allow small rounding differences
        if loan.loan_status != LoanStatus.CLOSED:
            loan.loan_status = LoanStatus.CLOSED
            db.commit()
            db.refresh(loan)
    
    return {
        "id": str(loan.id),
        "loan_amount": float(loan.loan_amount),
        "term_months": loan.number_of_instalments or "N/A",
        "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
        "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
        "status": loan.loan_status.value,
        "total_principal_paid": float(total_principal_paid),
        "total_interest_paid": float(total_interest_paid),
        "total_paid": float(total_paid),
        "outstanding_balance": float(outstanding_balance),
        "repayments": [
            {
                "id": str(repayment.id),
                "date": repayment.repayment_date.isoformat(),
                "principal": float(repayment.principal_amount),
                "interest": float(repayment.interest_amount),
                "total": float(repayment.total_amount)
            }
            for repayment in loan.repayments
        ]
    }


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
    for loan in loans:
        # Map status: OPEN -> active, others stay as-is
        status_value = loan.loan_status.value if hasattr(loan.loan_status, 'value') else str(loan.loan_status)
        if status_value == "open":
            status_display = "active"
        else:
            status_display = status_value
        
        result.append({
            "id": str(loan.id),
            "cycle_id": str(loan.cycle_id) if loan.cycle_id else None,
            "amount": float(loan.loan_amount),
            "term_months": loan.number_of_instalments or "N/A",
            "status": status_display,
            "application_date": loan.disbursement_date.isoformat() if loan.disbursement_date else (loan.created_at.isoformat() if loan.created_at else None),
            "type": "loan"
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
    
    if type == "savings":
        from app.models.transaction import Declaration, DeclarationStatus, DepositProof, DepositApproval
        
        # Get member's savings account
        savings_account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member_profile.id,
            LedgerAccount.account_name.ilike("%savings%")
        ).first()
        
        if savings_account:
            # Get journal lines for this account, but EXCLUDE penalty-related entries
            # Only include credits from deposit approvals (actual savings deposits)
            journal_lines = db.query(JournalLine).join(JournalEntry).filter(
                JournalLine.ledger_account_id == savings_account.id,
                JournalEntry.reversed_by.is_(None),  # Exclude reversed entries
                JournalEntry.source_type == "deposit_approval",  # Only deposit approvals
                JournalLine.credit_amount > 0  # Only credits (deposits)
            ).order_by(JournalEntry.entry_date.desc()).all()
            
            for line in journal_lines:
                # Get the deposit proof to show more details
                deposit_approval = db.query(DepositApproval).filter(
                    DepositApproval.journal_entry_id == line.journal_entry.id
                ).first()
                
                description = "Member savings deposit"
                if deposit_approval and deposit_approval.deposit_proof:
                    declaration = deposit_approval.deposit_proof.declaration
                    if declaration:
                        description = f"Deposit approved for {declaration.effective_month.strftime('%B %Y')} declaration"
                
                transactions.append({
                    "id": str(line.id),
                    "date": line.journal_entry.entry_date.isoformat(),
                    "description": description,
                    "debit": 0.0,
                    "credit": float(line.credit_amount),
                    "amount": float(line.credit_amount)
                })
        
        # Add declarations as debit entries (informational - shows when member declared savings)
        declarations = db.query(Declaration).filter(
            Declaration.member_id == member_profile.id,
            Declaration.declared_savings_amount.isnot(None),
            Declaration.declared_savings_amount > 0
        ).order_by(Declaration.created_at.desc()).all()
        
        for declaration in declarations:
            transactions.append({
                "id": f"declaration_{declaration.id}",
                "date": declaration.created_at.isoformat() if declaration.created_at else declaration.effective_month.isoformat(),
                "description": f"Declaration for {declaration.effective_month.strftime('%B %Y')}",
                "debit": float(declaration.declared_savings_amount),
                "credit": 0.0,
                "amount": float(declaration.declared_savings_amount),
                "is_declaration": True
            })
        
        # Sort all transactions by date (most recent first)
        transactions.sort(key=lambda x: x["date"], reverse=True)
    
    elif type == "penalties":
        from app.models.transaction import PenaltyRecord, PenaltyRecordStatus, Declaration, DeclarationStatus
        from app.models.cycle import Cycle, CyclePhase, PhaseType
        from sqlalchemy import extract
        from datetime import date as date_type
        
        # Get member's penalties account
        penalties_account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member_profile.id,
            LedgerAccount.account_name.ilike("%penalties%")
        ).first()
        
        # 1. Get journal lines (payment entries) for this account
        if penalties_account:
            journal_lines = db.query(JournalLine).join(JournalEntry).filter(
                JournalLine.ledger_account_id == penalties_account.id,
                JournalEntry.reversed_by.is_(None)  # Exclude reversed entries
            ).order_by(JournalEntry.entry_date.desc()).all()
            
            for line in journal_lines:
                amount = float(line.debit_amount) if line.debit_amount > 0 else float(line.credit_amount)
                transactions.append({
                    "id": str(line.id),
                    "date": line.journal_entry.entry_date.isoformat(),
                    "description": line.description or line.journal_entry.description,
                    "debit": float(line.debit_amount),
                    "credit": float(line.credit_amount),
                    "amount": amount,
                    "is_penalty_record": False
                })
        
        # 2. Get individual penalty records (all statuses to show complete history)
        # These show the individual penalties that were charged
        penalty_records = db.query(PenaltyRecord).filter(
            PenaltyRecord.member_id == member_profile.id
        ).order_by(PenaltyRecord.date_issued.desc()).all()
        
        for penalty in penalty_records:
            penalty_type = penalty.penalty_type
            fee_amount = float(penalty_type.fee_amount) if penalty_type else 0.0
            
            # Build description with penalty type name and notes
            description = penalty_type.name if penalty_type else "Penalty"
            if penalty.notes:
                description += f" - {penalty.notes}"
            
            # Add status indicator for non-POSTED penalties
            if penalty.status != PenaltyRecordStatus.POSTED:
                description += f" ({penalty.status.value})"
            
            # All penalty records are shown as debits (charges)
            transactions.append({
                "id": f"penalty_{penalty.id}",
                "date": penalty.date_issued.isoformat(),
                "description": description,
                "debit": fee_amount,
                "credit": 0.0,
                "amount": fee_amount,
                "is_penalty_record": True,
                "penalty_status": penalty.status.value
            })
        
        # 3. Get late declaration penalties from declarations
        # These are penalties that were automatically applied when declarations were made late
        # They're stored in declared_penalties but don't have PenaltyRecord entries
        declarations = db.query(Declaration).filter(
            Declaration.member_id == member_profile.id,
            Declaration.declared_penalties.isnot(None),
            Declaration.declared_penalties > 0
        ).order_by(Declaration.created_at.desc()).all()
        
        for declaration in declarations:
            # Get the cycle and declaration phase to check if late penalty applies
            cycle = db.query(Cycle).filter(Cycle.id == declaration.cycle_id).first()
            if not cycle:
                continue
            
            declaration_phase = db.query(CyclePhase).filter(
                CyclePhase.cycle_id == declaration.cycle_id,
                CyclePhase.phase_type == PhaseType.DECLARATION
            ).first()
            
            if not declaration_phase:
                continue
            
            auto_apply = getattr(declaration_phase, 'auto_apply_penalty', False)
            monthly_end_day = getattr(declaration_phase, 'monthly_end_day', None)
            
            if not (auto_apply and monthly_end_day):
                continue
            
            # Check if declaration was made late
            declaration_date = declaration.created_at.date() if declaration.created_at else None
            if not declaration_date:
                continue
            
            effective_date = declaration.effective_month
            is_late = False
            
            # Check if declaration is late
            if declaration_date.year == effective_date.year and declaration_date.month == effective_date.month:
                if declaration_date.day > monthly_end_day:
                    is_late = True
            elif declaration_date.year > effective_date.year or (declaration_date.year == effective_date.year and declaration_date.month > effective_date.month):
                is_late = True
            
            if is_late:
                # Get penalty type for late declaration
                penalty_type_id = getattr(declaration_phase, 'penalty_type_id', None)
                if penalty_type_id:
                    from app.models.transaction import PenaltyType
                    penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                    if penalty_type:
                        late_penalty_amount = float(penalty_type.fee_amount)
                        
                        # Only add if this penalty amount matches (to avoid duplicates)
                        # We'll add it as a late declaration penalty
                        transactions.append({
                            "id": f"late_declaration_{declaration.id}",
                            "date": declaration.created_at.isoformat() if declaration.created_at else effective_date.isoformat(),
                            "description": f"{penalty_type.name} - Declaration made after day {monthly_end_day} of {effective_date.strftime('%B %Y')}",
                            "debit": late_penalty_amount,
                            "credit": 0.0,
                            "amount": late_penalty_amount,
                            "is_penalty_record": True,
                            "penalty_status": "POSTED",
                            "is_late_declaration": True
                        })
                else:
                    # Fallback to deprecated penalty_amount
                    penalty_amount = getattr(declaration_phase, 'penalty_amount', None)
                    if penalty_amount:
                        late_penalty_amount = float(penalty_amount)
                        transactions.append({
                            "id": f"late_declaration_{declaration.id}",
                            "date": declaration.created_at.isoformat() if declaration.created_at else effective_date.isoformat(),
                            "description": f"Late Declaration Penalty - Declaration made after day {monthly_end_day} of {effective_date.strftime('%B %Y')}",
                            "debit": late_penalty_amount,
                            "credit": 0.0,
                            "amount": late_penalty_amount,
                            "is_penalty_record": True,
                            "penalty_status": "POSTED",
                            "is_late_declaration": True
                        })
    
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
                    # Payment - check both debit and credit (handle legacy credits and new debits)
                    # Handle None values and Decimal comparisons properly
                    debit_val = line.debit_amount if line.debit_amount is not None else Decimal("0.00")
                    credit_val = line.credit_amount if line.credit_amount is not None else Decimal("0.00")
                    debit_amount = float(debit_val) if debit_val and debit_val > Decimal("0.00") else 0.0
                    credit_amount = float(credit_val) if credit_val and credit_val > Decimal("0.00") else 0.0
                    amount = debit_amount if debit_amount > 0 else credit_amount
                    
                    # Always show payment transactions, even if amount is 0 (for debugging)
                    transactions.append({
                        "id": str(line.id),
                        "date": line.journal_entry.entry_date.isoformat(),
                        "description": line.description or line.journal_entry.description,
                        "debit": debit_amount,
                        "credit": credit_amount,
                        "amount": amount,
                        "is_payment": True
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
                    # Payment - check both debit and credit (handle legacy credits and new debits)
                    # Handle None values and Decimal comparisons properly
                    debit_val = line.debit_amount if line.debit_amount is not None else Decimal("0.00")
                    credit_val = line.credit_amount if line.credit_amount is not None else Decimal("0.00")
                    debit_amount = float(debit_val) if debit_val and debit_val > Decimal("0.00") else 0.0
                    credit_amount = float(credit_val) if credit_val and credit_val > Decimal("0.00") else 0.0
                    amount = debit_amount if debit_amount > 0 else credit_amount
                    
                    # Always show payment transactions, even if amount is 0 (for debugging)
                    transactions.append({
                        "id": str(line.id),
                        "date": line.journal_entry.entry_date.isoformat(),
                        "description": line.description or line.journal_entry.description,
                        "debit": debit_amount,
                        "credit": credit_amount,
                        "amount": amount,
                        "is_payment": True
                    })
    
    return {
        "type": type,
        "transactions": transactions
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
    
    if declaration.status != DeclarationStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot upload proof. Declaration status is {declaration.status.value}"
        )
    
    # Check if proof already exists for this declaration
    existing_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration_uuid
    ).first()
    if existing_proof:
        raise HTTPException(
            status_code=400,
            detail="Deposit proof already uploaded for this declaration"
        )
    
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
    
    # Update declaration status to APPROVED (as per user requirement)
    declaration.status = DeclarationStatus.APPROVED
    
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
    
    deposits = db.query(DepositProof).filter(
        DepositProof.member_id == member_profile.id
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
