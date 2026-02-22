from fastapi import APIRouter, Depends, HTTPException, Response, Form, UploadFile, File, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_treasurer, require_any_role, get_current_user
from app.models.user import User
from app.models.transaction import DepositProof, DepositProofStatus, DepositApproval, PenaltyRecord, PenaltyType, Declaration, DeclarationStatus, LoanApplication, LoanApplicationStatus, Loan, LoanStatus, BankStatement
from app.models.member import MemberProfile, MemberStatus
from app.models.user import User as UserModel
from app.services.transaction import approve_deposit, approve_penalty
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date as date_type
from decimal import Decimal
from app.core.config import BANK_STATEMENTS_DIR

router = APIRouter(prefix="/api/treasurer", tags=["treasurer"])


@router.get("/deposits/pending")
def get_pending_deposits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of pending deposit proofs awaiting approval with declaration details."""
    try:
        deposits = db.query(DepositProof).filter(
            DepositProof.status.in_([DepositProofStatus.SUBMITTED.value, DepositProofStatus.REJECTED.value])
        ).order_by(DepositProof.uploaded_at.desc()).all()
        
        if not deposits:
            return []
        
        result = []
        for dep in deposits:
            # Get member info
            member = db.query(MemberProfile).filter(MemberProfile.id == dep.member_id).first()
            user = None
            if member:
                user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
            
            # Get declaration details
            declaration = None
            if dep.declaration_id:
                declaration = db.query(Declaration).filter(Declaration.id == dep.declaration_id).first()
            
            result.append({
                "id": str(dep.id),
                "amount": float(dep.amount),
                "reference": dep.reference,
                "member_id": str(dep.member_id),
                "member_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
                "member_email": user.email if user else None,
                "declaration_id": str(dep.declaration_id) if dep.declaration_id else None,
                "effective_month": declaration.effective_month.isoformat() if declaration and declaration.effective_month else None,
                "declared_savings_amount": float(declaration.declared_savings_amount) if declaration and declaration.declared_savings_amount else None,
                "declared_social_fund": float(declaration.declared_social_fund) if declaration and declaration.declared_social_fund else None,
                "declared_admin_fund": float(declaration.declared_admin_fund) if declaration and declaration.declared_admin_fund else None,
                "declared_penalties": float(declaration.declared_penalties) if declaration and declaration.declared_penalties else None,
                "declared_interest_on_loan": float(declaration.declared_interest_on_loan) if declaration and declaration.declared_interest_on_loan else None,
                "declared_loan_repayment": float(declaration.declared_loan_repayment) if declaration and declaration.declared_loan_repayment else None,
                "uploaded_at": dep.uploaded_at.isoformat() if dep.uploaded_at else None,
                "upload_path": dep.upload_path,
                "treasurer_comment": dep.treasurer_comment,
                "member_response": dep.member_response,
                "rejected_at": dep.rejected_at.isoformat() if dep.rejected_at else None,
                "status": dep.status
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pending deposits: {str(e)}")


@router.get("/deposits/proof/{filename:path}")
def get_deposit_proof_file(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get deposit proof file for viewing/downloading."""
    from pathlib import Path
    from urllib.parse import unquote
    from app.core.config import DEPOSIT_PROOFS_DIR
    
    # Decode filename
    filename = unquote(filename)
    
    # Security: Only allow accessing files in the deposit_proofs directory
    # Extract just the filename (not full path) to prevent directory traversal
    safe_filename = Path(filename).name
    file_path = DEPOSIT_PROOFS_DIR / safe_filename
    
    # Verify file exists and is in the correct directory
    if not file_path.exists() or not str(file_path.resolve()).startswith(str(DEPOSIT_PROOFS_DIR.resolve())):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Verify user has permission (Treasurer or the member who uploaded it)
    deposit = db.query(DepositProof).filter(DepositProof.upload_path.like(f"%{safe_filename}")).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    
    # Check if user is treasurer or the member
    from app.models.member import MemberProfile
    member = db.query(MemberProfile).filter(MemberProfile.id == deposit.member_id).first()
    is_member = member and member.user_id == current_user.id
    is_treasurer = current_user.role and current_user.role.value.lower() in ['treasurer', 'admin', 'chairman']
    
    if not (is_member or is_treasurer):
        raise HTTPException(status_code=403, detail="You don't have permission to view this file")
    
    # Determine media type based on file extension
    ext = Path(safe_filename).suffix.lower()
    media_types = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif'
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type=media_type
    )


@router.post("/deposits/{deposit_id}/approve")
def approve_deposit_proof(
    deposit_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Approve deposit proof and post to ledger."""
    from app.models.ledger import LedgerAccount
    from uuid import UUID
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"=== DEPOSIT APPROVAL REQUEST START ===")
    logger.info(f"Deposit ID: {deposit_id}")
    logger.info(f"Approved by: {current_user.id} ({current_user.email})")
    
    try:
        deposit_uuid = UUID(deposit_id)
    except ValueError as e:
        logger.error(f"Invalid deposit ID format: {deposit_id}")
        raise HTTPException(status_code=400, detail="Invalid deposit ID format")
    
    # Get deposit proof
    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_uuid).first()
    if not deposit:
        logger.error(f"Deposit proof not found: {deposit_id}")
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    
    logger.info(f"Deposit found: ID={deposit.id}, Status={deposit.status}, Amount={deposit.amount}, Member={deposit.member_id}")
    
    # Allow approval of both SUBMITTED and REJECTED proofs
    # REJECTED proofs can be approved if treasurer is satisfied with member's response
    if deposit.status not in [DepositProofStatus.SUBMITTED.value, DepositProofStatus.REJECTED.value]:
        logger.error(f"Deposit cannot be approved. Current status: {deposit.status}")
        raise HTTPException(
            status_code=400,
            detail=f"Deposit proof cannot be approved. Current status: {deposit.status}"
        )
    
    # Get member to find their accounts
    member = db.query(MemberProfile).filter(MemberProfile.id == deposit.member_id).first()
    if not member:
        logger.error(f"Member not found for deposit: {deposit.member_id}")
        raise HTTPException(status_code=404, detail="Member not found")
    
    logger.info(f"Member found: ID={member.id}, Status={member.status}")
    
    # Get account IDs
    bank_cash = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "BANK_CASH"
    ).first()
    
    if not bank_cash:
        logger.error("BANK_CASH account not found")
        raise HTTPException(status_code=500, detail="BANK_CASH ledger account not found")
    
    # Get or create member-specific savings account
    member_savings = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == deposit.member_id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    
    if not member_savings:
        # Create savings account if it doesn't exist
        from app.models.ledger import AccountType
        short_id = str(deposit.member_id).replace('-', '')[:8]
        member_savings = LedgerAccount(
            account_code=f"MEM_SAV_{short_id}",
            account_name=f"Member Savings - {deposit.member_id}",
            account_type=AccountType.LIABILITY,
            member_id=deposit.member_id,
            description=f"Savings account for member {deposit.member_id}"
        )
        db.add(member_savings)
        db.flush()  # Flush to get the ID without committing
        logger.info(f"Created member savings account: {member_savings.id} for member: {deposit.member_id}")
    
    logger.info(f"Found accounts: BANK_CASH={bank_cash.id}, Member Savings={member_savings.id}")
    
    # Get member-specific Social Fund and Admin Fund accounts
    member_social_fund = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == deposit.member_id,
        LedgerAccount.account_name.ilike("%social fund%")
    ).first()
    
    member_admin_fund = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == deposit.member_id,
        LedgerAccount.account_name.ilike("%admin fund%")
    ).first()
    
    penalties_payable = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == deposit.member_id,
        LedgerAccount.account_name.ilike("%penalties payable%")
    ).first()
    
    interest_income = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_INCOME"
    ).first()
    
    loans_receivable = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == deposit.member_id,
        LedgerAccount.account_name.ilike("%loan%receivable%")
    ).first()
    
    logger.info(f"Optional accounts: Social Fund={member_social_fund.id if member_social_fund else None}, "
                f"Admin Fund={member_admin_fund.id if member_admin_fund else None}, "
                f"Penalties={penalties_payable.id if penalties_payable else None}, "
                f"Interest Income={interest_income.id if interest_income else None}, "
                f"Loans Receivable={loans_receivable.id if loans_receivable else None}")
    
    # Member-specific social/admin fund accounts may not exist if member hasn't made first declaration yet
    # In that case, they'll be None and approve_deposit will handle it
    
    try:
        logger.info("Calling approve_deposit service function")
        approval = approve_deposit(
            db=db,
            deposit_proof_id=deposit_uuid,
            approved_by=current_user.id,
            bank_cash_account_id=bank_cash.id,
            member_savings_account_id=member_savings.id,
            member_social_fund_account_id=member_social_fund.id if member_social_fund else None,
            member_admin_fund_account_id=member_admin_fund.id if member_admin_fund else None,
            penalties_payable_account_id=penalties_payable.id if penalties_payable else None,
            interest_income_account_id=interest_income.id if interest_income else None,
            loans_receivable_account_id=loans_receivable.id if loans_receivable else None
        )
        logger.info(f"Deposit approved successfully. Approval ID: {approval.id}")
        logger.info(f"=== DEPOSIT APPROVAL REQUEST SUCCESS ===")
        # Check and transfer any excess social/admin fund contributions to savings
        from app.models.cycle import Cycle, CycleStatus
        from app.services.transaction import post_excess_contributions
        active_cycle = db.query(Cycle).filter(
            Cycle.status == CycleStatus.ACTIVE
        ).first()
        if active_cycle:
            declaration = db.query(Declaration).filter(
                Declaration.id == deposit.declaration_id
            ).first()
            eff_month = declaration.effective_month if declaration else date_type.today()
            post_excess_contributions(
                db=db,
                member_id=deposit.member_id,
                cycle=active_cycle,
                effective_month=eff_month,
                approved_by=current_user.id,
            )
        # Get member name for audit
        _member_user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
        _member_name = f"{_member_user.first_name or ''} {_member_user.last_name or ''}".strip() if _member_user else str(member.id)
        from app.core.audit import write_audit_log
        write_audit_log(
            user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
            user_role=current_user.role.value if current_user.role else "treasurer",
            action="Deposit approved",
            details=f"member={_member_name}, amount=K {deposit.amount}"
        )
        return {"message": "Deposit approved and posted to ledger successfully", "approval_id": str(approval.id)}
    except Exception as e:
        import traceback
        error_type = type(e).__name__
        error_msg = str(e)
        tb_str = traceback.format_exc()
        
        logger.error(f"=== DEPOSIT APPROVAL FAILED ===")
        logger.error(f"Deposit ID: {deposit_id}")
        logger.error(f"Error Type: {error_type}")
        logger.error(f"Error Message: {error_msg}")
        logger.error(f"Full Traceback:\n{tb_str}")
        logger.error(f"=== END DEPOSIT APPROVAL ERROR ===")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve deposit: {error_msg} (Type: {error_type})"
        )


@router.post("/deposits/{deposit_id}/reject")
def reject_deposit_proof(
    deposit_id: str,
    comment: str = Form(...),
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Reject deposit proof with a comment for the member to address."""
    from uuid import UUID
    from datetime import datetime
    
    try:
        deposit_uuid = UUID(deposit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deposit ID format")
    
    # Get deposit proof
    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_uuid).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    
    # Allow rejection of both SUBMITTED and REJECTED proofs
    # REJECTED proofs can have their rejection comment updated
    if deposit.status not in [DepositProofStatus.SUBMITTED.value, DepositProofStatus.REJECTED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Deposit proof cannot be rejected. Current status: {deposit.status}"
        )
    
    # Update deposit proof status to REJECTED
    deposit.status = DepositProofStatus.REJECTED.value
    deposit.treasurer_comment = comment
    deposit.rejected_by = current_user.id
    deposit.rejected_at = datetime.utcnow()
    
    # Reset declaration status back to PENDING so member can edit it
    if deposit.declaration_id:
        declaration = db.query(Declaration).filter(Declaration.id == deposit.declaration_id).first()
        if declaration:
            declaration.status = DeclarationStatus.PENDING
    
    db.commit()
    db.refresh(deposit)

    # Get member name for audit
    _rej_member = db.query(MemberProfile).filter(MemberProfile.id == deposit.member_id).first()
    _rej_user = db.query(UserModel).filter(UserModel.id == _rej_member.user_id).first() if _rej_member else None
    _rej_name = f"{_rej_user.first_name or ''} {_rej_user.last_name or ''}".strip() if _rej_user else str(deposit.member_id)
    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Deposit rejected",
        details=f"member={_rej_name}"
    )
    return {
        "message": "Deposit proof rejected. Member can now respond and update their declaration.",
        "deposit_id": str(deposit.id)
    }


@router.post("/journal-entries/{journal_entry_id}/reverse")
def reverse_journal_entry(
    journal_entry_id: str,
    reason: str = Form(...),
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Reverse/withdraw a journal entry that was posted by error."""
    from uuid import UUID
    from datetime import datetime
    from app.models.ledger import JournalEntry, JournalLine
    from app.services.accounting import create_journal_entry
    
    try:
        entry_uuid = UUID(journal_entry_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid journal entry ID format")
    
    # Get the original journal entry
    original_entry = db.query(JournalEntry).filter(JournalEntry.id == entry_uuid).first()
    if not original_entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    
    # Check if already reversed
    if original_entry.reversed_by:
        raise HTTPException(status_code=400, detail="This journal entry has already been reversed")
    
    # Get all journal lines
    lines = db.query(JournalLine).filter(JournalLine.journal_entry_id == entry_uuid).all()
    if not lines:
        raise HTTPException(status_code=400, detail="Journal entry has no lines")
    
    # Create reversing entry (swap debits and credits)
    reversing_lines = []
    for line in lines:
        reversing_lines.append({
            "account_id": line.ledger_account_id,
            "debit_amount": line.credit_amount,  # Swap
            "credit_amount": line.debit_amount,  # Swap
            "description": f"Reversal: {line.description or 'Original entry'}"
        })
    
    # Create the reversing journal entry
    reversing_entry = create_journal_entry(
        db=db,
        description=f"Reversal of entry {original_entry.id} - {reason}",
        lines=reversing_lines,
        cycle_id=original_entry.cycle_id,
        source_ref=str(original_entry.id),
        source_type="reversal",
        created_by=current_user.id
    )
    
    # Mark original entry as reversed
    original_entry.reversed_by = current_user.id
    original_entry.reversed_at = datetime.utcnow()
    original_entry.reversal_reason = reason
    
    db.commit()
    db.refresh(reversing_entry)
    
    return {
        "message": "Journal entry reversed successfully",
        "original_entry_id": str(original_entry.id),
        "reversing_entry_id": str(reversing_entry.id)
    }


@router.get("/penalty-types")
def get_penalty_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all penalty types."""
    try:
        penalty_types = db.query(PenaltyType).filter(PenaltyType.enabled == "1").all()
        if not penalty_types:
            return []
        return [{
            "id": str(pt.id),
            "name": pt.name,
            "description": pt.description,
            "fee_amount": str(pt.fee_amount)
        } for pt in penalty_types]
    except Exception:
        return {"message": "To be done - penalty types functionality"}


@router.post("/penalty-types")
def create_penalty_type(
    name: str,
    description: str,
    fee_amount: float,
    current_user: User = Depends(require_any_role("Treasurer", "Compliance", "Admin", "Chairman")),
    db: Session = Depends(get_db)
):
    """Create a new penalty type. Accessible by Treasurer, Compliance, Admin, and Chairman."""
    penalty_type = PenaltyType(
        name=name,
        description=description,
        fee_amount=fee_amount,
        enabled="1"
    )
    db.add(penalty_type)
    db.commit()
    db.refresh(penalty_type)
    return {
        "message": "Penalty type created successfully",
        "penalty_type": {
            "id": str(penalty_type.id),
            "name": penalty_type.name,
            "description": penalty_type.description,
            "fee_amount": str(penalty_type.fee_amount)
        }
    }


@router.get("/penalties/pending")
def get_pending_penalties(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of pending penalties awaiting approval."""
    try:
        from app.models.transaction import PenaltyRecordStatus
        penalties = db.query(PenaltyRecord).filter(
            PenaltyRecord.status == PenaltyRecordStatus.PENDING
        ).all()
        if not penalties:
            return []
        result = []
        for penalty in penalties:
            penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty.penalty_type_id).first()
            member = db.query(MemberProfile).filter(MemberProfile.id == penalty.member_id).first()
            user = None
            if member:
                user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
            
            result.append({
                "id": str(penalty.id),
                "member_id": str(penalty.member_id),
                "member_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
                "member_email": user.email if user else None,
                "date_issued": penalty.date_issued.isoformat() if penalty.date_issued else None,
                "notes": penalty.notes,
                "penalty_type": {
                    "name": penalty_type.name if penalty_type else None,
                    "fee_amount": str(penalty_type.fee_amount) if penalty_type else None
                } if penalty_type else None
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading pending penalties: {str(e)}")


@router.post("/penalties/{penalty_id}/approve")
def approve_penalty_record(
    penalty_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Approve penalty and post to ledger."""
    from app.models.ledger import LedgerAccount
    
    try:
        penalty_uuid = UUID(penalty_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid penalty ID format")
    
    # Get penalty record
    penalty = db.query(PenaltyRecord).filter(PenaltyRecord.id == penalty_uuid).first()
    if not penalty:
        raise HTTPException(status_code=404, detail="Penalty record not found")
    
    # Get member to find their specific savings account
    member = db.query(MemberProfile).filter(MemberProfile.id == penalty.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Get or create member-specific savings account
    member_savings = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member.id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    
    if not member_savings:
        # Create savings account if it doesn't exist
        from app.models.ledger import AccountType
        short_id = str(member.id).replace('-', '')[:8]
        member_savings = LedgerAccount(
            account_code=f"MEM_SAV_{short_id}",
            account_name=f"Member Savings - {member.id}",
            account_type=AccountType.LIABILITY,
            member_id=member.id,
            description=f"Savings account for member {member.id}"
        )
        db.add(member_savings)
        db.flush()
    
    # Get penalty income account
    penalty_income = db.query(LedgerAccount).filter(LedgerAccount.account_code == "PENALTY_INCOME").first()
    
    if not penalty_income:
        raise HTTPException(status_code=500, detail="Penalty income account not found. Please run the setup script to create required accounts.")
    
    try:
        penalty = approve_penalty(
            db=db,
            penalty_record_id=penalty_uuid,
            approved_by=current_user.id,
            member_savings_account_id=member_savings.id,
            penalty_income_account_id=penalty_income.id
        )
        _pen_user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
        _pen_name = f"{_pen_user.first_name or ''} {_pen_user.last_name or ''}".strip() if _pen_user else str(member.id)
        from app.core.audit import write_audit_log
        write_audit_log(
            user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
            user_role=current_user.role.value if current_user.role else "treasurer",
            action="Penalty approved",
            details=f"member={_pen_name}"
        )
        return {"message": "Penalty approved and charged to member account successfully", "penalty_id": str(penalty.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log the full error for debugging
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error approving penalty: {str(e)}")


@router.get("/credit-rating/scheme")
def get_credit_rating_scheme(
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Get credit rating scheme."""
    from app.models.policy import CreditRatingScheme
    scheme = db.query(CreditRatingScheme).order_by(CreditRatingScheme.effective_from.desc()).first()
    return scheme


@router.post("/members/{member_id}/credit-rating")
def assign_credit_rating(
    member_id: str,
    tier_id: str,
    cycle_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Assign credit rating to a member."""
    from app.models.policy import MemberCreditRating, CreditRatingTier

    try:
        member_uuid = UUID(member_id)
        tier_uuid = UUID(tier_id)
        cycle_uuid = UUID(cycle_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == tier_uuid).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Credit rating tier not found")

    rating = MemberCreditRating(
        member_id=member_uuid,
        cycle_id=cycle_uuid,
        tier_id=tier_uuid,
        scheme_id=tier.scheme_id,
        assigned_by=current_user.id
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return {"message": "Credit rating assigned successfully", "rating": rating}


@router.get("/loans/pending")
def get_pending_loan_applications(
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Get list of pending loan applications awaiting approval."""
    applications = db.query(LoanApplication).filter(
        LoanApplication.status == LoanApplicationStatus.PENDING
    ).order_by(LoanApplication.application_date.desc()).all()
    
    result = []
    for app in applications:
        member = db.query(MemberProfile).filter(MemberProfile.id == app.member_id).first()
        user = None
        if member:
            user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
        
        result.append({
            "id": str(app.id),
            "member_id": str(app.member_id),
            "member_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
            "member_email": user.email if user else None,
            "amount": float(app.amount),
            "term_months": app.term_months,
            "notes": app.notes,
            "application_date": app.application_date.isoformat() if app.application_date else None,
            "cycle_id": str(app.cycle_id)
        })
    
    return result


@router.get("/loans/approved")
def get_approved_loans(
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Get list of approved loans awaiting disbursement."""
    loans = db.query(Loan).filter(
        Loan.loan_status == LoanStatus.APPROVED
    ).order_by(Loan.created_at.desc()).all()
    
    result = []
    for loan in loans:
        member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
        user = None
        if member:
            user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
        
        result.append({
            "id": str(loan.id),
            "application_id": str(loan.application_id) if loan.application_id else None,
            "member_id": str(loan.member_id),
            "member_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
            "member_email": user.email if user else None,
            "loan_amount": float(loan.loan_amount),
            "term_months": loan.number_of_instalments or "N/A",
            "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
            "created_at": loan.created_at.isoformat() if loan.created_at else None,
            "cycle_id": str(loan.cycle_id)
        })
    
    return result


@router.get("/loans/active")
def get_active_loans(
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Get list of active loans (OPEN or DISBURSED status).
    Reconciliation-created loans use DISBURSED; normally disbursed loans use OPEN.
    """
    from app.models.transaction import Declaration, DeclarationStatus
    from decimal import Decimal
    from sqlalchemy import or_

    loans = db.query(Loan).filter(
        Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED])
    ).order_by(Loan.created_at.desc()).all()

    result = []
    for loan in loans:
        member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
        user = None
        if member:
            user = db.query(UserModel).filter(UserModel.id == member.user_id).first()

        # Compute paid amounts from approved declarations (covers pre- and post-fix data)
        decl_q = db.query(Declaration).filter(
            Declaration.member_id == loan.member_id,
            Declaration.status == DeclarationStatus.APPROVED,
            or_(
                Declaration.declared_loan_repayment > 0,
                Declaration.declared_interest_on_loan > 0,
            ),
        )
        if loan.disbursement_date:
            decl_q = decl_q.filter(Declaration.effective_month >= loan.disbursement_date)
        paid_decls = decl_q.all()

        total_principal_paid = sum(
            (d.declared_loan_repayment or Decimal("0.00")) for d in paid_decls
        )
        total_interest_paid = sum(
            (d.declared_interest_on_loan or Decimal("0.00")) for d in paid_decls
        )
        outstanding_balance = max(Decimal("0.00"), loan.loan_amount - total_principal_paid)

        result.append({
            "id": str(loan.id),
            "application_id": str(loan.application_id) if loan.application_id else None,
            "member_id": str(loan.member_id),
            "member_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
            "member_email": user.email if user else None,
            "loan_amount": float(loan.loan_amount),
            "term_months": loan.number_of_instalments or "N/A",
            "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
            "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
            "created_at": loan.created_at.isoformat() if loan.created_at else None,
            "cycle_id": str(loan.cycle_id),
            "status": loan.loan_status.value,
            "total_principal_paid": float(total_principal_paid),
            "total_interest_paid": float(total_interest_paid),
            "total_paid": float(total_principal_paid + total_interest_paid),
            "outstanding_balance": float(outstanding_balance),
            "repayment_count": len(paid_decls),
        })

    return result


@router.get("/loans/{loan_id}/details")
def get_loan_details(
    loan_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Get detailed information about a loan including repayment history and performance."""
    from decimal import Decimal
    from datetime import date, timedelta
    
    try:
        loan_uuid = UUID(loan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid loan ID format")
    
    loan = db.query(Loan).filter(Loan.id == loan_uuid).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
    user = None
    if member:
        user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
    
    # Compute payment history from approved declarations (covers all historical data)
    from app.models.transaction import Declaration, DeclarationStatus
    from sqlalchemy import or_

    decl_q = db.query(Declaration).filter(
        Declaration.member_id == loan.member_id,
        Declaration.status == DeclarationStatus.APPROVED,
        or_(
            Declaration.declared_loan_repayment > 0,
            Declaration.declared_interest_on_loan > 0,
        ),
    )
    if loan.disbursement_date:
        decl_q = decl_q.filter(Declaration.effective_month >= loan.disbursement_date)
    paid_decls = decl_q.order_by(Declaration.effective_month.asc()).all()

    total_principal_paid = Decimal("0.00")
    total_interest_paid = Decimal("0.00")
    repayments_list = []
    running_balance = loan.loan_amount

    for decl in paid_decls:
        principal = decl.declared_loan_repayment or Decimal("0.00")
        interest = decl.declared_interest_on_loan or Decimal("0.00")
        total_principal_paid += principal
        total_interest_paid += interest
        running_balance -= principal
        repayments_list.append({
            "id": f"decl_{decl.id}",
            "date": decl.effective_month.isoformat(),
            "principal": float(principal),
            "interest": float(interest),
            "total": float(principal + interest),
            "balance": float(max(Decimal("0.00"), running_balance)),
            "is_on_time": True,
        })

    outstanding_balance = max(Decimal("0.00"), loan.loan_amount - total_principal_paid)
    payment_performance = "On Time"

    return {
        "id": str(loan.id),
        "application_id": str(loan.application_id) if loan.application_id else None,
        "member_id": str(loan.member_id),
        "member_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
        "member_email": user.email if user else None,
        "loan_amount": float(loan.loan_amount),
        "term_months": loan.number_of_instalments or "N/A",
        "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
        "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "cycle_id": str(loan.cycle_id),
        "status": loan.loan_status.value,
        "total_principal_paid": float(total_principal_paid),
        "total_interest_paid": float(total_interest_paid),
        "total_paid": float(total_principal_paid + total_interest_paid),
        "outstanding_balance": float(outstanding_balance),
        "payment_performance": payment_performance,
        "all_payments_on_time": True,
        "repayments": repayments_list,
    }


@router.post("/loans/{application_id}/approve")
def approve_loan_application(
    application_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Approve a loan application, create Loan record, disburse it, and post to ledger in one step."""
    from app.models.cycle import Cycle
    from app.models.policy import MemberCreditRating, CreditRatingInterestRange
    from app.models.ledger import LedgerAccount
    from app.services.transaction import disburse_loan
    from decimal import Decimal
    from datetime import date
    
    try:
        app_uuid = UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid application ID format")
    
    application = db.query(LoanApplication).filter(LoanApplication.id == app_uuid).first()
    if not application:
        raise HTTPException(status_code=404, detail="Loan application not found")
    
    if application.status != LoanApplicationStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve application with status: {application.status.value}"
        )
    
    # Get credit rating to determine interest rate
    credit_rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == application.member_id,
        MemberCreditRating.cycle_id == application.cycle_id
    ).first()
    
    if not credit_rating:
        raise HTTPException(
            status_code=400,
            detail="Member does not have a credit rating for this cycle"
        )
    
    # Get interest rate for the loan term
    interest_range = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == credit_rating.tier_id,
        CreditRatingInterestRange.cycle_id == application.cycle_id,
        (CreditRatingInterestRange.term_months == application.term_months) | (CreditRatingInterestRange.term_months.is_(None))
    ).first()
    
    if not interest_range:
        raise HTTPException(
            status_code=400,
            detail="Interest rate not configured for this loan term and credit rating"
        )
    
    # Get ledger accounts for disbursement
    bank_cash = db.query(LedgerAccount).filter(LedgerAccount.account_code == "BANK_CASH").first()
    loans_receivable = db.query(LedgerAccount).filter(LedgerAccount.account_code.like("LOANS_RECEIVABLE%")).first()
    
    if not all([bank_cash, loans_receivable]):
        raise HTTPException(status_code=500, detail="Required ledger accounts not found")
    
    # Create Loan record
    loan = Loan(
        application_id=application.id,
        member_id=application.member_id,
        cycle_id=application.cycle_id,
        loan_amount=application.amount,
        percentage_interest=interest_range.effective_rate_percent,
        number_of_instalments=application.term_months,
        loan_status=LoanStatus.APPROVED  # Will be changed to OPEN after disbursement
    )
    db.add(loan)
    db.flush()  # Flush to get the loan ID
    
    # Update application status
    application.status = LoanApplicationStatus.APPROVED
    application.reviewed_by = current_user.id
    application.reviewed_at = datetime.utcnow()
    
    # Disburse the loan (post to ledger and set status to OPEN)
    # This happens in the same transaction - disburse_loan will commit
    try:
        loan = disburse_loan(
            db=db,
            loan_id=loan.id,  # Pass UUID directly
            disbursed_by=current_user.id,
            bank_cash_account_id=bank_cash.id,
            loans_receivable_account_id=loans_receivable.id
        )
    except Exception as e:
        # If disbursement fails, rollback the loan creation
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disburse loan: {str(e)}"
        )
    
    _loan_member = db.query(MemberProfile).filter(MemberProfile.id == application.member_id).first()
    _loan_user = db.query(UserModel).filter(UserModel.id == _loan_member.user_id).first() if _loan_member else None
    _loan_name = f"{_loan_user.first_name or ''} {_loan_user.last_name or ''}".strip() if _loan_user else str(application.member_id)
    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Loan approved & disbursed",
        details=f"member={_loan_name}, amount=K {application.amount}"
    )
    return {
        "message": "Loan approved, disbursed, and posted to member's account successfully",
        "loan_id": str(loan.id),
        "application_id": str(application.id)
    }


@router.post("/loans/{loan_id}/disburse")
def disburse_loan_endpoint(
    loan_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Disburse an approved loan, post to ledger, and change status to OPEN (active)."""
    from app.models.ledger import LedgerAccount
    from app.services.transaction import disburse_loan

    try:
        loan_uuid = UUID(loan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid loan ID format")

    # Get account IDs
    bank_cash = db.query(LedgerAccount).filter(LedgerAccount.account_code == "BANK_CASH").first()
    loans_receivable = db.query(LedgerAccount).filter(LedgerAccount.account_code.like("LOANS_RECEIVABLE%")).first()

    if not all([bank_cash, loans_receivable]):
        raise HTTPException(status_code=500, detail="Required ledger accounts not found")

    loan = disburse_loan(
        db=db,
        loan_id=loan_uuid,
        disbursed_by=current_user.id,
        bank_cash_account_id=bank_cash.id,
        loans_receivable_account_id=loans_receivable.id
    )
    
    return {"message": "Loan disbursed successfully and is now active", "loan_id": str(loan.id)}


@router.get("/reports/declarations")
def get_declarations_report(
    month: Optional[str] = None,  # Format: YYYY-MM-DD (first day of month)
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get all members with their declarations for a specific month. Returns all members, showing declaration amount if exists, and payment status."""
    from sqlalchemy import extract, and_, or_
    from datetime import date, datetime
    
    # Parse month parameter or use current month
    if month:
        try:
            target_date = datetime.strptime(month, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")
    else:
        today = date.today()
        target_date = date(today.year, today.month, 1)
    
    from app.models.user import UserRoleEnum

    # Get all active members
    members = db.query(MemberProfile).filter(
        MemberProfile.status == MemberStatus.ACTIVE
    ).all()

    result = []
    for member in members:
        user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
        if not user:
            continue

        # Exclude admin users from the report
        if user.role == UserRoleEnum.ADMIN:
            continue

        member_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not member_name:
            continue

        # Find declaration for this month (include all statuses: PENDING, PROOF, APPROVED, etc.)
        declaration = db.query(Declaration).filter(
            and_(
                Declaration.member_id == member.id,
                extract('year', Declaration.effective_month) == target_date.year,
                extract('month', Declaration.effective_month) == target_date.month
            )
        ).first()

        # Calculate total declaration amount (None if no declaration)
        declaration_amount = None
        if declaration:
            total = Decimal("0.00")
            if declaration.declared_savings_amount:
                total += declaration.declared_savings_amount
            if declaration.declared_social_fund:
                total += declaration.declared_social_fund
            if declaration.declared_admin_fund:
                total += declaration.declared_admin_fund
            if declaration.declared_penalties:
                total += declaration.declared_penalties
            if declaration.declared_interest_on_loan:
                total += declaration.declared_interest_on_loan
            if declaration.declared_loan_repayment:
                total += declaration.declared_loan_repayment
            declaration_amount = float(total) if total > 0 else None

        # Check if deposit proof is approved (paid)
        is_paid = False
        if declaration:
            deposit_proof = db.query(DepositProof).filter(
                DepositProof.declaration_id == declaration.id,
                DepositProof.status == DepositProofStatus.APPROVED.value
            ).first()
            is_paid = deposit_proof is not None

        # Include ALL members (with or without declarations)
        result.append({
            "member_id": str(member.id),
            "member_name": member_name,
            "declaration_amount": declaration_amount,
            "is_paid": is_paid
        })
    
    # Sort by member name
    result.sort(key=lambda x: x["member_name"])
    
    return {
        "month": target_date.isoformat(),
        "members": result
    }


@router.get("/reports/declarations/details")
def get_declaration_details_report(
    member_id: Optional[str] = None,
    month: Optional[str] = None,
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get declaration details for a member and month (view-only, for Reports modal)."""
    from sqlalchemy import extract, and_
    from datetime import date, datetime

    if not member_id or not month:
        raise HTTPException(status_code=400, detail="member_id and month are required")

    try:
        member_uuid = UUID(member_id)
        target_date = datetime.strptime(month, "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail="Invalid member_id or month format. Use YYYY-MM-DD for month.")

    member = db.query(MemberProfile).filter(
        MemberProfile.id == member_uuid,
        MemberProfile.status == MemberStatus.ACTIVE
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    member_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Unknown"

    declaration = db.query(Declaration).filter(
        and_(
            Declaration.member_id == member_uuid,
            extract("year", Declaration.effective_month) == target_date.year,
            extract("month", Declaration.effective_month) == target_date.month
        )
    ).first()

    if not declaration:
        return {
            "member_id": str(member.id),
            "member_name": member_name,
            "effective_month": target_date.isoformat(),
            "has_declaration": False,
            "declaration": None,
            "deposit_proof": None,
        }

    total = Decimal("0.00")
    for attr in ("declared_savings_amount", "declared_social_fund", "declared_admin_fund",
                 "declared_penalties", "declared_interest_on_loan", "declared_loan_repayment"):
        v = getattr(declaration, attr, None)
        if v is not None:
            total += v

    deposit_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration.id
    ).order_by(DepositProof.uploaded_at.desc()).first()

    return {
        "member_id": str(member.id),
        "member_name": member_name,
        "effective_month": declaration.effective_month.isoformat(),
        "has_declaration": True,
        "declaration": {
            "id": str(declaration.id),
            "declared_savings_amount": float(declaration.declared_savings_amount) if declaration.declared_savings_amount is not None else None,
            "declared_social_fund": float(declaration.declared_social_fund) if declaration.declared_social_fund is not None else None,
            "declared_admin_fund": float(declaration.declared_admin_fund) if declaration.declared_admin_fund is not None else None,
            "declared_penalties": float(declaration.declared_penalties) if declaration.declared_penalties is not None else None,
            "declared_interest_on_loan": float(declaration.declared_interest_on_loan) if declaration.declared_interest_on_loan is not None else None,
            "declared_loan_repayment": float(declaration.declared_loan_repayment) if declaration.declared_loan_repayment is not None else None,
            "total": float(total),
            "status": declaration.status.value,
        },
        "deposit_proof": {
            "id": str(deposit_proof.id),
            "status": deposit_proof.status,
            "amount": float(deposit_proof.amount),
            "uploaded_at": deposit_proof.uploaded_at.isoformat() if deposit_proof.uploaded_at else None,
        } if deposit_proof else None,
    }


@router.get("/reports/loans")
def get_loans_report(
    month: Optional[str] = Query(None, description="YYYY-MM-DD — filter by disbursement month"),
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get loans disbursed in the given month (defaults to current month)."""
    from sqlalchemy import extract, and_

    # Determine target year/month
    if month:
        try:
            target_date = datetime.strptime(month[:10], "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    target_year = target_date.year
    target_month = target_date.month

    # Query all loans disbursed in the target month (both normal OPEN and reconciliation DISBURSED)
    loans = db.query(Loan).filter(
        Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED]),
        extract("year", Loan.disbursement_date) == target_year,
        extract("month", Loan.disbursement_date) == target_month,
    ).order_by(Loan.disbursement_date.asc()).all()

    result = []
    for loan in loans:
        member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
        user = db.query(UserModel).filter(UserModel.id == member.user_id).first() if member else None
        if not user:
            continue

        member_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not member_name:
            continue

        result.append({
            "loan_id": str(loan.id),
            "member_id": str(loan.member_id),
            "member_name": member_name,
            "loan_amount": float(loan.loan_amount),
            "is_approved": True,
            "is_disbursed": True,
            "is_paid": True,
        })

    result.sort(key=lambda x: x["member_name"])

    return {"loans": result}


# ---------------------------------------------------------------------------
# Bank Statement endpoints
# ---------------------------------------------------------------------------

ALLOWED_STMT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


@router.post("/bank-statements")
async def upload_bank_statement(
    file: UploadFile = File(...),
    month: str = Form(...),  # YYYY-MM-DD
    description: Optional[str] = Form(None),
    cycle_id: Optional[str] = Form(None),
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Upload a bank statement PDF/image for the active (or specified) cycle."""
    from pathlib import Path
    from app.models.cycle import Cycle, CycleStatus

    # Validate month
    try:
        stmt_month = datetime.strptime(month, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")

    # Resolve cycle
    if cycle_id:
        try:
            cycle_uuid = UUID(cycle_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cycle_id format")
        cycle = db.query(Cycle).filter(Cycle.id == cycle_uuid).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found")
    else:
        cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="No active cycle found")

    # Validate file extension
    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_STMT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_STMT_EXTENSIONS)}")

    # Build safe filename
    short_cycle_id = str(cycle.id).replace("-", "")[:8]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_original = "".join(c if c.isalnum() or c in "._-" else "_" for c in original_name)
    filename = f"stmt_{short_cycle_id}_{timestamp}_{safe_original}"

    # Ensure directory exists
    BANK_STATEMENTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = BANK_STATEMENTS_DIR / filename

    # Save file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Persist record
    stmt = BankStatement(
        cycle_id=cycle.id,
        statement_month=stmt_month,
        description=description,
        upload_path=str(file_path),
        uploaded_by=current_user.id
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)

    return {
        "message": "Bank statement uploaded successfully",
        "id": str(stmt.id),
        "filename": filename
    }


@router.get("/bank-statements")
def list_bank_statements(
    cycle_id: Optional[str] = None,
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """List bank statements for the active (or specified) cycle."""
    from pathlib import Path
    from app.models.cycle import Cycle, CycleStatus

    if cycle_id:
        try:
            cycle_uuid = UUID(cycle_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cycle_id format")
    else:
        cycle = db.query(Cycle).filter(Cycle.status == CycleStatus.ACTIVE).first()
        if not cycle:
            return {"statements": []}
        cycle_uuid = cycle.id

    stmts = (
        db.query(BankStatement)
        .filter(BankStatement.cycle_id == cycle_uuid)
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


@router.put("/bank-statements/{statement_id}")
async def update_bank_statement(
    statement_id: str,
    description: Optional[str] = Form(None),
    month: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Edit description/month and optionally replace the file for a bank statement."""
    from pathlib import Path

    try:
        stmt_uuid = UUID(statement_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid statement ID format")

    stmt = db.query(BankStatement).filter(BankStatement.id == stmt_uuid).first()
    if not stmt:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    if month is not None:
        try:
            stmt.statement_month = datetime.strptime(month, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")

    if description is not None:
        stmt.description = description

    if file and file.filename:
        original_name = file.filename
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_STMT_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_STMT_EXTENSIONS)}")

        short_cycle_id = str(stmt.cycle_id).replace("-", "")[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_original = "".join(c if c.isalnum() or c in "._-" else "_" for c in original_name)
        filename = f"stmt_{short_cycle_id}_{timestamp}_{safe_original}"

        BANK_STATEMENTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = BANK_STATEMENTS_DIR / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        stmt.upload_path = str(file_path)

    db.commit()
    db.refresh(stmt)
    return {"message": "Bank statement updated successfully", "id": str(stmt.id)}


@router.get("/bank-statements/file/{filename:path}")
def get_bank_statement_file(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Serve a bank statement file (accessible by Treasurer, Chairman, Admin, and Member)."""
    from pathlib import Path
    from urllib.parse import unquote

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
