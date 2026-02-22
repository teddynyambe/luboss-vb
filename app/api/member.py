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
    get_member_admin_fund_payments
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
            
            # Check if declaration is late (after monthly_end_day)
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
                            # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                            penalty_obj = PenaltyRecord(
                                id=uuid.uuid4(),
                                member_id=member_profile.id,
                                penalty_type_id=penalty_type_id,
                                status=PenaltyRecordStatus.APPROVED,
                                created_by=system_user_id,
                                notes=f"Late Declaration - Declaration made after day {monthly_end_day} of {effective_date.strftime('%B %Y')} (Declaration period ends on day {monthly_end_day})",
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
            "rejected_deposit_proof": rejected_deposit_proof
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
                        from app.services.transaction import get_system_user_id
                        system_user_id = get_system_user_id(db)
                        if not system_user_id:
                            # If no admin exists, skip penalty creation (shouldn't happen in production)
                            import logging
                            logging.warning(f"No admin user found to create system penalty for member {member_profile.id}")
                        else:
                            # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                            late_penalty = PenaltyRecord(
                                member_id=member_profile.id,
                                penalty_type_id=penalty_type_id,
                                status=PenaltyRecordStatus.APPROVED.value,  # Use .value to ensure lowercase string is sent
                                created_by=system_user_id,  # Use admin user for system-generated penalties
                                notes=f"Late Loan Application - Loan application submitted after day {monthly_end_day} of {today.strftime('%B %Y')} (Loan application period ends on day {monthly_end_day})"
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

    return {
        "id": str(loan.id),
        "loan_amount": float(loan.loan_amount),
        "term_months": loan.number_of_instalments or "N/A",
        "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
        "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
        "status": loan.loan_status.value,
        "total_principal_paid": float(total_principal_paid),
        "total_interest_paid": float(total_interest_paid),
        "total_paid": float(total_principal_paid + total_interest_paid),
        "outstanding_balance": float(outstanding_balance),
        "repayments": repayment_items,
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
            
            # Add declarations as debit entries (informational - shows when member declared savings)
            declarations = db.query(Declaration).filter(
                Declaration.member_id == member_profile.id,
                Declaration.declared_savings_amount.isnot(None),
                Declaration.declared_savings_amount > 0
            ).order_by(Declaration.created_at.desc()).all()
            
            for declaration in declarations:
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
                    }
                })
            
            # Include excess contribution transfers (internal reclassifications to savings)
            exc_savings_account = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_profile.id,
                LedgerAccount.account_name.ilike("%savings%")
            ).first()
            if exc_savings_account:
                excess_lines = db.query(JournalLine).join(JournalEntry).filter(
                    JournalLine.ledger_account_id == exc_savings_account.id,
                    JournalEntry.source_type == "excess_contribution",
                    JournalEntry.reversed_by.is_(None),
                    JournalLine.credit_amount > 0,
                ).all()
                for line in excess_lines:
                    je = line.journal_entry
                    entry_date = (
                        je.entry_date.date().isoformat()
                        if je.entry_date else date.today().isoformat()
                    )
                    transactions.append({
                        "id": f"excess_{je.id}",
                        "date": entry_date,
                        "description": je.description,
                        "debit": 0.0,
                        "credit": float(line.credit_amount),
                        "amount": float(line.credit_amount),
                        "is_declaration": False,
                    })

            # Sort all transactions by date (most recent first)
            transactions.sort(key=lambda x: x["date"], reverse=True)

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
    
    except Exception as e:
        import logging
        import traceback
        logging.error(f"Error fetching {type} transactions: {str(e)}", exc_info=True)
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching {type} transactions: {str(e)}"
        )
    
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
                        from app.services.transaction import get_system_user_id
                        system_user_id = get_system_user_id(db)
                        if not system_user_id:
                            # If no admin exists, skip penalty creation (shouldn't happen in production)
                            import logging
                            logging.warning(f"No admin user found to create system penalty for member {member_profile.id}")
                        else:
                            # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                            late_penalty = PenaltyRecord(
                                member_id=member_profile.id,
                                penalty_type_id=penalty_type_id,
                                status=PenaltyRecordStatus.APPROVED.value,  # Use .value to ensure lowercase string is sent
                                created_by=system_user_id,  # Use admin user for system-generated penalties
                                notes=f"Late Deposits - Deposit submitted after day {monthly_end_day} of {next_month_name} (Deposit period: {start_s} of {effective_name} to {end_s} of {next_month_name})"
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

    # ── helper: aggregate journal credits per account_id ─────────────────────
    def _credit_sum(acc_ids: list, before: datetime = None, since: datetime = None,
                    source_type: str = None) -> dict:
        if not acc_ids:
            return {}
        q = (
            db.query(JournalLine.ledger_account_id, sqlfunc.sum(JournalLine.credit_amount))
            .join(JournalEntry)
            .filter(
                JournalLine.ledger_account_id.in_(acc_ids),
                JournalLine.credit_amount > 0,
                JournalEntry.reversed_by.is_(None)
            )
        )
        if source_type:
            q = q.filter(JournalEntry.source_type == source_type)
        if before is not None:
            q = q.filter(JournalEntry.entry_date < before)
        if since is not None:
            q = q.filter(JournalEntry.entry_date >= since)
        return {str(acc_id): float(v or 0) for acc_id, v in q.group_by(JournalLine.ledger_account_id).all()}

    def _member_val(accs: dict, amounts: dict, member_id) -> float:
        acc = accs.get(member_id)
        return amounts.get(str(acc.id), 0.0) if acc else 0.0

    sav_ids    = [a.id for a in savings_accs.values()]
    social_ids = [a.id for a in social_accs.values()]
    admin_ids  = [a.id for a in admin_accs.values()]

    sav_bf_map    = _credit_sum(sav_ids,    before=month_start, source_type="deposit_approval")
    sav_month_map = _credit_sum(sav_ids,    since=month_start, before=month_end, source_type="deposit_approval")
    social_bf_map = _credit_sum(social_ids, before=month_start, source_type="deposit_approval")
    admin_bf_map  = _credit_sum(admin_ids,  before=month_start, source_type="deposit_approval")

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
        social_admin_bf = (_member_val(social_accs, social_bf_map, member.id) +
                           _member_val(admin_accs,  admin_bf_map,  member.id))

        interest_bf = round((savings_bf / total_savings_bf) * total_interest_bf, 2) \
            if total_savings_bf > 0 else 0.0

        loan_amount_total = sum(float(l.loan_amount) for l in all_loans.get(mid, []))
        loan_bf = max(0.0, loan_amount_total - prior_repayments_by_member.get(mid, 0.0))

        decl = declarations.get(mid)
        savings_declared      = float(decl.declared_savings_amount or 0) if decl else 0.0
        social_admin_declared = (float(decl.declared_social_fund or 0) +
                                 float(decl.declared_admin_fund   or 0)) if decl else 0.0

        penalty_total = sum(
            float(penalty_types_map[str(p.penalty_type_id)].fee_amount)
            for p in penalties_month.get(mid, [])
            if str(p.penalty_type_id) in penalty_types_map
        )

        approved_decl = approved_decl_month_by_member.get(mid)
        repayment_principal = float(approved_decl.declared_loan_repayment or 0) if approved_decl else 0.0
        repayment_interest  = float(approved_decl.declared_interest_on_loan or 0) if approved_decl else 0.0

        total_deposited = _member_val(savings_accs, sav_month_map, member.id)

        # Interest earned = member's share of this month's loan interest income,
        # weighted by their approved deposit (not savings B/F)
        interest_earned = round((total_deposited / total_group_deposited) * total_interest_month, 2) \
            if total_group_deposited > 0 else 0.0

        loan_applied = interest_on_loan_applied = 0.0
        for loan in all_loans.get(mid, []):
            if loan.disbursement_date and target_date <= loan.disbursement_date < next_month_date:
                loan_applied             += float(loan.loan_amount)
                interest_on_loan_applied += float(loan.loan_amount) * float(loan.percentage_interest) / 100

        rows.append({
            "name":                     name,
            "savings_bf":               round(savings_bf, 2),
            "social_admin_bf":          round(social_admin_bf, 2),
            "interest_bf":              round(interest_bf, 2),
            "loan_bf":                  round(loan_bf, 2),
            "savings_declared":         round(savings_declared, 2),
            "social_admin_declared":    round(social_admin_declared, 2),
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
        "savings_bf", "social_admin_bf", "interest_bf", "loan_bf",
        "savings_declared", "social_admin_declared", "penalty",
        "loan_repayment", "interest_on_loan_paid", "total_deposited",
        "interest_earned", "loan_applied", "interest_on_loan_applied",
    ]
    totals = {k: round(sum(r[k] for r in rows), 2) for k in num_keys}
    totals["name"] = "TOTAL"

    return {"month": target_date.isoformat(), "members": rows, "totals": totals}
