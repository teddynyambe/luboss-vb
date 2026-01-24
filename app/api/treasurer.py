from fastapi import APIRouter, Depends, HTTPException, Response, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.core.dependencies import require_treasurer, require_any_role, get_current_user
from app.models.user import User
from app.models.transaction import DepositProof, DepositProofStatus, DepositApproval, PenaltyRecord, PenaltyType, Declaration, DeclarationStatus, LoanApplication, LoanApplicationStatus, Loan, LoanStatus
from app.models.member import MemberProfile
from app.models.user import User as UserModel
from app.services.transaction import approve_deposit, approve_penalty
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from datetime import datetime

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
    
    try:
        deposit_uuid = UUID(deposit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deposit ID format")
    
    # Get deposit proof
    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_uuid).first()
    if not deposit:
        raise HTTPException(status_code=404, detail="Deposit proof not found")
    
    # Allow approval of both SUBMITTED and REJECTED proofs
    # REJECTED proofs can be approved if treasurer is satisfied with member's response
    if deposit.status not in [DepositProofStatus.SUBMITTED.value, DepositProofStatus.REJECTED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Deposit proof cannot be approved. Current status: {deposit.status}"
        )
    
    # Get member to find their accounts
    member = db.query(MemberProfile).filter(MemberProfile.id == deposit.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Get account IDs
    bank_cash = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "BANK_CASH"
    ).first()
    
    # Get member-specific savings account
    member_savings = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == deposit.member_id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    
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
    
    if not all([bank_cash, member_savings]):
        raise HTTPException(status_code=500, detail="Required ledger accounts not found")
    
    # Member-specific social/admin fund accounts may not exist if member hasn't made first declaration yet
    # In that case, they'll be None and approve_deposit will handle it
    
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
    return {"message": "Deposit approved and posted to ledger successfully", "approval_id": str(approval.id)}


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
    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail="Credit rating tier not found")
    
    rating = MemberCreditRating(
        member_id=member_id,
        cycle_id=cycle_id,
        tier_id=tier_id,
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
    """Get list of active loans (OPEN status)."""
    loans = db.query(Loan).filter(
        Loan.loan_status == LoanStatus.OPEN
    ).order_by(Loan.created_at.desc()).all()
    
    result = []
    for loan in loans:
        member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
        user = None
        if member:
            user = db.query(UserModel).filter(UserModel.id == member.user_id).first()
        
        # Calculate payment summary
        total_principal_paid = sum(repayment.principal_amount for repayment in loan.repayments)
        total_interest_paid = sum(repayment.interest_amount for repayment in loan.repayments)
        total_paid = total_principal_paid + total_interest_paid
        outstanding_balance = loan.loan_amount - total_principal_paid
        
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
            "total_principal_paid": float(total_principal_paid),
            "total_interest_paid": float(total_interest_paid),
            "total_paid": float(total_paid),
            "outstanding_balance": float(outstanding_balance),
            "repayment_count": len(loan.repayments)
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
    
    # Calculate payment summary
    total_principal_paid = Decimal("0.00")
    total_interest_paid = Decimal("0.00")
    total_paid = Decimal("0.00")
    
    repayments_list = []
    for repayment in loan.repayments:
        total_principal_paid += repayment.principal_amount
        total_interest_paid += repayment.interest_amount
        total_paid += repayment.total_amount
        
        # Calculate if payment was on time
        # For now, we'll consider a payment on time if it's within the same month as expected
        # In a real system, you'd compare against scheduled due dates
        is_on_time = True  # Default - can be enhanced with due date logic
        
        repayments_list.append({
            "id": str(repayment.id),
            "date": repayment.repayment_date.isoformat(),
            "principal": float(repayment.principal_amount),
            "interest": float(repayment.interest_amount),
            "total": float(repayment.total_amount),
            "is_on_time": is_on_time
        })
    
    outstanding_balance = loan.loan_amount - total_principal_paid
    
    # Calculate payment performance
    all_payments_on_time = all(rep["is_on_time"] for rep in repayments_list)
    payment_performance = "On Time" if all_payments_on_time else "Some Late Payments"
    
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
        "total_paid": float(total_paid),
        "outstanding_balance": float(outstanding_balance),
        "payment_performance": payment_performance,
        "all_payments_on_time": all_payments_on_time,
        "repayments": repayments_list
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
    
    return {
        "message": "Loan approved, disbursed, and posted to member's account successfully",
        "loan_id": str(loan.id),
        "application_id": str(application.id)
    }


@router.post("/loans/{loan_id}/disburse")
def disburse_loan(
    loan_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Disburse an approved loan, post to ledger, and change status to OPEN (active)."""
    from app.models.ledger import LedgerAccount
    from app.services.transaction import disburse_loan
    
    # Get account IDs
    bank_cash = db.query(LedgerAccount).filter(LedgerAccount.account_code == "BANK_CASH").first()
    loans_receivable = db.query(LedgerAccount).filter(LedgerAccount.account_code.like("LOANS_RECEIVABLE%")).first()
    
    if not all([bank_cash, loans_receivable]):
        raise HTTPException(status_code=500, detail="Required ledger accounts not found")
    
    loan = disburse_loan(
        db=db,
        loan_id=loan_id,
        disbursed_by=current_user.id,
        bank_cash_account_id=bank_cash.id,
        loans_receivable_account_id=loans_receivable.id
    )
    
    return {"message": "Loan disbursed successfully and is now active", "loan_id": str(loan.id)}
