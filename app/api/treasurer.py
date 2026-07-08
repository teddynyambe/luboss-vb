from fastapi import APIRouter, Depends, HTTPException, Response, Form, UploadFile, File, status, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
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


@router.get("/reports/interest-revenue")
def get_interest_revenue_report_endpoint(
    cycle_id: str | None = None,
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db),
):
    """Interest revenue rollup + drill-down.

    Recognises full expected interest at loan origination (accrual basis).
    Optional cycle_id filter scopes to a single cycle; omit for all-time.
    """
    from app.services.interest_revenue_report import get_interest_revenue_report
    return get_interest_revenue_report(db, cycle_id=cycle_id)


@router.get("/deposits/pending")
def get_pending_deposits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of pending deposit proofs awaiting approval with declaration details.

    Includes:
      - all SUBMITTED proofs (newly uploaded by member, awaiting treasurer review)
      - REJECTED proofs that have a member_response (member pushed back, asking
        treasurer to reconsider)

    Plain REJECTED proofs without a member response are NOT included — they're
    dead-ends in the treasurer's queue (the next action is on the member, who
    needs to upload a new proof). Excluding them keeps the queue actionable.
    """
    try:
        deposits = db.query(DepositProof).filter(
            or_(
                DepositProof.status == DepositProofStatus.SUBMITTED.value,
                and_(
                    DepositProof.status == DepositProofStatus.REJECTED.value,
                    DepositProof.member_response.isnot(None),
                    DepositProof.member_response != "",
                ),
            )
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
                "member_name": f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() if user else "Unknown",
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
        LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
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
        # Automatic transfer of excess Social/Admin Fund contributions to
        # Savings has been disabled. It produced negative Social/Admin Fund
        # balances on reports and made reconciliation confusing. Overpayments
        # now stay in the fund account they were declared under; if a real
        # reclassification is needed the treasurer can do it via Posted
        # Transactions → Split.
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
    
    # Create the reversing journal entry — bucket it under the original's dealing month
    # so the reversal lands in the same reporting period as the entry it reverses.
    reversing_entry = create_journal_entry(
        db=db,
        description=f"Reversal of entry {original_entry.id} - {reason}",
        lines=reversing_lines,
        dealing_month=original_entry.dealing_month,
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
                "member_name": f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() if user else "Unknown",
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
    """Get list of pending loan applications awaiting approval.

    Each application is annotated with a `pending_payoff` object when the
    member has an outstanding active loan AND a PENDING/PROOF declaration
    that commits to covering the payoff. Treasurers should approve+disburse
    only after the payoff deposit is approved so they don't stack loans.
    """
    from decimal import Decimal as _D
    applications = db.query(LoanApplication).filter(
        LoanApplication.status == LoanApplicationStatus.PENDING
    ).order_by(LoanApplication.application_date.desc()).all()

    result = []
    for app in applications:
        member = db.query(MemberProfile).filter(MemberProfile.id == app.member_id).first()
        user = None
        if member:
            user = db.query(UserModel).filter(UserModel.id == member.user_id).first()

        # Detect the "pending payoff" case: member has an active loan with
        # outstanding balance and has already declared enough to pay it off.
        pending_payoff = None
        active_loan = db.query(Loan).filter(
            Loan.member_id == app.member_id,
            Loan.loan_status.in_([LoanStatus.APPROVED, LoanStatus.DISBURSED, LoanStatus.OPEN]),
        ).order_by(Loan.disbursement_date.asc()).first()
        if active_loan:
            total_p_repaid = sum(
                _D(str(rep.principal_amount or 0)) for rep in active_loan.repayments
            )
            total_i_repaid = sum(
                _D(str(rep.interest_amount or 0)) for rep in active_loan.repayments
            )
            outstanding_p = _D(str(active_loan.loan_amount or 0)) - total_p_repaid
            expected_interest = (
                _D(str(active_loan.loan_amount or 0))
                * _D(str(active_loan.percentage_interest or 0))
                / _D("100")
            )
            outstanding_i = expected_interest - total_i_repaid
            total_outstanding = (
                max(_D("0.00"), outstanding_p) + max(_D("0.00"), outstanding_i)
            )
            if total_outstanding > _D("0.01"):
                # Sum the member's pending / proof declarations' committed
                # loan repayment + interest.
                from app.models.transaction import DeclarationStatus as _DS
                declared_payoff = _D("0.00")
                pending_decls = db.query(Declaration).filter(
                    Declaration.member_id == app.member_id,
                    Declaration.status.in_([_DS.PENDING, _DS.PROOF]),
                ).all()
                for d in pending_decls:
                    declared_payoff += _D(str(d.declared_loan_repayment or 0))
                    declared_payoff += _D(str(d.declared_interest_on_loan or 0))

                if declared_payoff + _D("0.01") >= total_outstanding:
                    loan_label = (
                        active_loan.disbursement_date.strftime("%B %Y")
                        if active_loan.disbursement_date
                        else "undisbursed"
                    )
                    pending_payoff = {
                        "loan_id": str(active_loan.id),
                        "loan_short_id": str(active_loan.id)[:8],
                        "loan_month_label": loan_label,
                        "loan_amount": float(active_loan.loan_amount or 0),
                        "outstanding_principal": float(max(_D("0.00"), outstanding_p)),
                        "outstanding_interest": float(max(_D("0.00"), outstanding_i)),
                        "outstanding_total": float(total_outstanding),
                        "declared_payoff": float(declared_payoff),
                    }

        result.append({
            "id": str(app.id),
            "member_id": str(app.member_id),
            "member_name": f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() if user else "Unknown",
            "member_email": user.email if user else None,
            "amount": float(app.amount),
            "term_months": app.term_months,
            "notes": app.notes,
            "application_date": app.application_date.isoformat() if app.application_date else None,
            "cycle_id": str(app.cycle_id),
            "pending_payoff": pending_payoff,
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
            "member_name": f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() if user else "Unknown",
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
    loan_filter: str = "active",
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get loans by filter.
    loan_filter='active'      → all OPEN + DISBURSED (default)
    loan_filter='at_risk'     → OPEN/DISBURSED, no payment in 30+ days, still within term
    loan_filter='defaulting'  → OPEN/DISBURSED, past maturity, outstanding > 0
    loan_filter='paid'        → CLOSED (paid-off loans)
    """
    import logging
    logger = logging.getLogger(__name__)
    from app.models.transaction import Repayment
    from app.models.ledger import JournalEntry
    from decimal import Decimal
    from sqlalchemy import func
    from datetime import date as _date_cls, timedelta as _td

    if loan_filter == "paid":
        statuses = [LoanStatus.CLOSED]
    else:
        statuses = [LoanStatus.OPEN, LoanStatus.DISBURSED]

    today = _date_cls.today()

    loans = db.query(Loan).filter(
        Loan.loan_status.in_(statuses)
    ).order_by(Loan.created_at.desc()).all()

    # Drop loans whose disbursement JE has been reversed — the Loan row stays
    # in the DB for audit, but the loan no longer represents real money on the
    # books and shouldn't appear in any Loans tab (Active / At Risk / Defaulting
    # / Paid Off). Filtering here once keeps every downstream calc clean.
    from app.services.loan_repair import loan_has_live_disbursement
    loans = [L for L in loans if loan_has_live_disbursement(db, L.id)]

    result = []
    for loan in loans:
        try:
            member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
            user = None
            if member:
                user = db.query(UserModel).filter(UserModel.id == member.user_id).first()

            # Paid amounts are sourced from Repayment rows with a live (non-reversed)
            # journal entry — same source the statement uses, so the figures here
            # match what the member sees.
            paid_principal_sum, paid_interest_sum, repayment_count = (
                db.query(
                    func.coalesce(func.sum(Repayment.principal_amount), 0),
                    func.coalesce(func.sum(Repayment.interest_amount), 0),
                    func.count(Repayment.id),
                )
                .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
                .filter(
                    Repayment.loan_id == loan.id,
                    JournalEntry.reversed_by.is_(None),
                    JournalEntry.reversed_at.is_(None),
                )
                .one()
            )
            total_principal_paid = Decimal(str(paid_principal_sum))
            total_interest_paid = Decimal(str(paid_interest_sum))
            outstanding_balance = max(Decimal("0.00"), loan.loan_amount - total_principal_paid)
            rate = float(loan.percentage_interest or 0)
            # Interest is a flat charge on the principal (not compounded per month)
            total_interest_expected = float(loan.loan_amount) * (rate / 100) if rate > 0 else None

            # Auto-close fully-paid loans in real-time
            interest_expected_dec = Decimal(str(total_interest_expected)) if total_interest_expected else Decimal("0.00")
            if (outstanding_balance <= Decimal("0.01")
                    and total_interest_paid >= interest_expected_dec
                    and loan.loan_status != LoanStatus.CLOSED):
                loan.loan_status = LoanStatus.CLOSED
                db.commit()
                db.refresh(loan)
                # Skip this loan from the active list since it's now closed
                if loan_filter != "paid":
                    continue

            status_val = loan.loan_status.value if hasattr(loan.loan_status, "value") else str(loan.loan_status)

            # Compute maturity date from disbursement + term months.
            # Use stdlib instead of dateutil to avoid an extra dependency.
            maturity_date = None
            if loan.disbursement_date and loan.number_of_instalments:
                try:
                    term = int(loan.number_of_instalments)
                    d = loan.disbursement_date
                    new_month = d.month - 1 + term
                    new_year = d.year + new_month // 12
                    new_month = new_month % 12 + 1
                    # Clamp day to the last day of the target month if needed
                    import calendar
                    last_day = calendar.monthrange(new_year, new_month)[1]
                    new_day = min(d.day, last_day)
                    from datetime import date as _date
                    maturity_date = _date(new_year, new_month, new_day).isoformat()
                except (ValueError, TypeError):
                    pass

            # Performance classification:
            #   defaulting → active loan past maturity with outstanding > 0
            #   at_risk    → active loan, no payment yet, at least 30 days old
            #                (still within term, or term unknown)
            #   on_track   → everything else active
            #   paid       → closed loan
            performance_status = "on_track"
            if loan.loan_status == LoanStatus.CLOSED:
                performance_status = "paid"
            else:
                maturity_dt = None
                if maturity_date:
                    try:
                        maturity_dt = _date_cls.fromisoformat(maturity_date)
                    except ValueError:
                        maturity_dt = None
                is_defaulting = (
                    maturity_dt is not None
                    and maturity_dt < today
                    and outstanding_balance > Decimal("0.01")
                )
                no_payment_made = (
                    total_principal_paid == Decimal("0.00")
                    and total_interest_paid == Decimal("0.00")
                )
                created_dt = loan.created_at.date() if loan.created_at else today
                aged_30d = (today - created_dt) >= _td(days=30)
                is_at_risk = (
                    not is_defaulting
                    and no_payment_made
                    and aged_30d
                    and (maturity_dt is None or maturity_dt >= today)
                )
                if is_defaulting:
                    performance_status = "defaulting"
                elif is_at_risk:
                    performance_status = "at_risk"

            # Apply requested filter
            if loan_filter == "at_risk" and performance_status != "at_risk":
                continue
            if loan_filter == "defaulting" and performance_status != "defaulting":
                continue

            result.append({
                "id": str(loan.id),
                "application_id": str(loan.application_id) if loan.application_id else None,
                "member_id": str(loan.member_id),
                "member_name": f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() if user else "Unknown",
                "member_email": user.email if user else None,
                "loan_amount": float(loan.loan_amount),
                "term_months": loan.number_of_instalments or "N/A",
                "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
                "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
                "maturity_date": maturity_date,
                "created_at": loan.created_at.isoformat() if loan.created_at else None,
                "cycle_id": str(loan.cycle_id) if loan.cycle_id else None,
                "status": status_val,
                "performance_status": performance_status,
                "total_principal_paid": float(total_principal_paid),
                "total_interest_paid": float(total_interest_paid),
                "total_interest_expected": total_interest_expected,
                "total_paid": float(total_principal_paid + total_interest_paid),
                "outstanding_balance": float(outstanding_balance),
                "repayment_count": int(repayment_count or 0),
            })
        except Exception as e:
            logger.error(f"Error processing loan {loan.id}: {e}", exc_info=True)
            continue

    return result


@router.get("/loans/{loan_id}/details")
def get_loan_details(
    loan_id: str,
    current_user: User = Depends(require_any_role("Treasurer", "Chairman", "Admin")),
    db: Session = Depends(get_db)
):
    """Get detailed information about a loan including repayment history and performance."""
    from decimal import Decimal
    from datetime import date, timedelta
    from app.models.transaction import Repayment
    from app.models.ledger import JournalEntry
    
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
    
    # Payment history sourced from live Repayment rows (same source the statement
    # and the active-loans list use, so the numbers stay aligned everywhere).
    repayments_q = (
        db.query(Repayment, JournalEntry)
        .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
        .filter(
            Repayment.loan_id == loan.id,
            JournalEntry.reversed_by.is_(None),
            JournalEntry.reversed_at.is_(None),
        )
        .order_by(Repayment.repayment_date.asc())
        .all()
    )

    total_principal_paid = Decimal("0.00")
    total_interest_paid = Decimal("0.00")
    repayments_list = []
    running_balance = loan.loan_amount

    for rep, _je in repayments_q:
        principal = rep.principal_amount or Decimal("0.00")
        interest = rep.interest_amount or Decimal("0.00")
        total_principal_paid += principal
        total_interest_paid += interest
        running_balance -= principal
        repayments_list.append({
            "id": str(rep.id),
            "date": rep.repayment_date.isoformat() if rep.repayment_date else None,
            "principal": float(principal),
            "interest": float(interest),
            "total": float(principal + interest),
            "balance": float(max(Decimal("0.00"), running_balance)),
            "is_on_time": True,
        })

    outstanding_balance = max(Decimal("0.00"), loan.loan_amount - total_principal_paid)
    rate = float(loan.percentage_interest or 0)
    # Interest is a flat charge on the principal (not compounded per month)
    total_interest_expected = float(loan.loan_amount) * (rate / 100) if rate > 0 else None

    # Maturity from disbursement + term months (stdlib, no dateutil dependency).
    maturity_date = None
    maturity_dt = None
    if loan.disbursement_date and loan.number_of_instalments:
        try:
            term = int(loan.number_of_instalments)
            d = loan.disbursement_date
            new_month = d.month - 1 + term
            new_year = d.year + new_month // 12
            new_month = new_month % 12 + 1
            import calendar
            last_day = calendar.monthrange(new_year, new_month)[1]
            new_day = min(d.day, last_day)
            maturity_dt = date(new_year, new_month, new_day)
            maturity_date = maturity_dt.isoformat()
        except (ValueError, TypeError):
            pass

    # Performance label — same rules as the active-loans list so badges align.
    today = date.today()
    if loan.loan_status == LoanStatus.CLOSED:
        performance_status = "paid"
    elif (
        maturity_dt is not None
        and maturity_dt < today
        and outstanding_balance > Decimal("0.01")
    ):
        performance_status = "defaulting"
    elif (
        total_principal_paid == Decimal("0.00")
        and total_interest_paid == Decimal("0.00")
        and loan.created_at
        and (today - loan.created_at.date()) >= timedelta(days=30)
        and (maturity_dt is None or maturity_dt >= today)
    ):
        performance_status = "at_risk"
    else:
        performance_status = "on_track"

    performance_label = {
        "paid": "Paid Off",
        "defaulting": "Defaulting — past maturity",
        "at_risk": "At Risk — no payment yet",
        "on_track": "On Time",
    }[performance_status]
    all_payments_on_time = performance_status in ("on_track", "paid")

    return {
        "id": str(loan.id),
        "application_id": str(loan.application_id) if loan.application_id else None,
        "member_id": str(loan.member_id),
        "member_name": f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() if user else "Unknown",
        "member_email": user.email if user else None,
        "loan_amount": float(loan.loan_amount),
        "term_months": loan.number_of_instalments or "N/A",
        "interest_rate": float(loan.percentage_interest) if loan.percentage_interest else None,
        "disbursement_date": loan.disbursement_date.isoformat() if loan.disbursement_date else None,
        "maturity_date": maturity_date,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "cycle_id": str(loan.cycle_id),
        "status": loan.loan_status.value,
        "performance_status": performance_status,
        "total_principal_paid": float(total_principal_paid),
        "total_interest_paid": float(total_interest_paid),
        "total_interest_expected": total_interest_expected,
        "total_paid": float(total_principal_paid + total_interest_paid),
        "outstanding_balance": float(outstanding_balance),
        "payment_performance": performance_label,
        "all_payments_on_time": all_payments_on_time,
        "repayments": repayments_list,
    }


class ApproveLoanRequest(BaseModel):
    """Optional overrides the treasurer can apply when approving a loan.

    Use when the group has less cash on hand than the requested amount, or
    when an adjusted term is being agreed. The application record is updated
    in place so the audit trail reflects what was actually disbursed.
    """
    amount: Optional[float] = None         # disbursed amount (overrides application.amount)
    term_months: Optional[str] = None      # actual term (overrides application.term_months)
    note: Optional[str] = None             # reason for the variation; appended to application.notes
    # Optional surcharge penalty — when set, a pending PenaltyRecord of this
    # type is created against the member at disbursement (e.g. "Emergency
    # Loan" K150 for out-of-window borrowing). The member will see and pay
    # it on their next declaration just like any other pending penalty.
    surcharge_penalty_type_id: Optional[str] = None


@router.post("/loans/{application_id}/approve")
def approve_loan_application(
    application_id: str,
    force: bool = False,
    body: Optional[ApproveLoanRequest] = None,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db)
):
    """Approve a loan application, create Loan record, disburse it, and post to ledger in one step.

    Enforces one active loan per member. Pass `?force=true` (Admin only) to
    override — used for genuine refinance/restructure cases.

    The optional request body lets the treasurer adjust the disbursed amount
    and/or term at approval time and attach a note. The application record is
    updated in place so the saved figures match what was actually disbursed.
    """
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

    # Enforce one active loan per member.
    #   - Live new application (application_date today): only Admin can force-override.
    #   - Backdated historical reconciliation (application_date in the past):
    #     Treasurer can force-override too, because the loan being approved
    #     existed in a prior period and the conflict is a chronological
    #     artefact, not a current double-borrow. The follow-on reconciliation
    #     that records the historical repayment will close the loan.
    existing_active = db.query(Loan).filter(
        Loan.member_id == application.member_id,
        Loan.loan_status.in_([LoanStatus.APPROVED, LoanStatus.OPEN, LoanStatus.DISBURSED]),
    ).first()
    if existing_active:
        is_admin = (current_user.role and current_user.role.value.lower() == "admin")
        app_dt = application.application_date.date() if application.application_date else date.today()
        is_backdated = app_dt < date.today()
        can_override = (force and is_admin) or (force and is_backdated)
        if not can_override:
            detail = (
                f"Member already has an active loan (status={existing_active.loan_status.value}, "
                f"amount=K{existing_active.loan_amount}). Close or consolidate it before approving "
                "a new one."
            )
            if is_backdated:
                detail += (
                    " This application is backdated; Treasurer may resubmit with force=true "
                    "to record the historical loan, then reconcile its payoff."
                )
            else:
                detail += " Admins may pass force=true to override."
            raise HTTPException(status_code=409, detail=detail)
    
    # Apply treasurer overrides (if any) to the application before any further
    # lookups, so the rate-table lookup honors the actual term being approved.
    override_amount: Decimal = None
    override_term: str = None
    override_note: str = None
    if body:
        if body.amount is not None:
            override_amount = Decimal(str(body.amount))
            if override_amount <= 0:
                raise HTTPException(status_code=400, detail="Override amount must be positive.")
        if body.term_months:
            override_term = body.term_months.strip() or None
        if body.note:
            override_note = body.note.strip() or None
    if override_amount is not None:
        application.amount = override_amount
    if override_term:
        application.term_months = override_term
    if override_note:
        prefix = (application.notes + "\n") if application.notes else ""
        application.notes = (
            f"{prefix}[Treasurer @ approval, {datetime.utcnow().date().isoformat()}]: "
            f"{override_note}"
        )
    if override_amount is not None or override_term or override_note:
        db.flush()

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
    # This happens in the same transaction - disburse_loan will commit.
    # If the application was backdated (reconciliation), use its application_date
    # as the disbursement date so the loan's borrowing/maturity reflect when the
    # member actually borrowed the money, not when the treasurer is approving it.
    today_dt = date.today()
    backdated_disbursement = None
    if application.application_date and application.application_date.date() < today_dt:
        backdated_disbursement = application.application_date.date()
    try:
        loan = disburse_loan(
            db=db,
            loan_id=loan.id,  # Pass UUID directly
            disbursed_by=current_user.id,
            bank_cash_account_id=bank_cash.id,
            loans_receivable_account_id=loans_receivable.id,
            disbursement_date_override=backdated_disbursement,
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
    from app.models.transaction import PenaltyRecordStatus

    # Optional surcharge penalty (e.g. Emergency Loan K150). Created PENDING so
    # the member sees it on their next declaration and pays for it like any
    # other pending penalty. Surcharge is independent of the loan's ledger
    # post — it lands in the standard penalty bucket so the existing
    # declaration / deposit / approve_penalty flow handles posting.
    surcharge_record_id = None
    surcharge_name = None
    if body and body.surcharge_penalty_type_id:
        try:
            surcharge_uuid = UUID(body.surcharge_penalty_type_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid surcharge_penalty_type_id format")
        surcharge_type = db.query(PenaltyType).filter(
            PenaltyType.id == surcharge_uuid,
            PenaltyType.enabled == "1",
        ).first()
        if not surcharge_type:
            raise HTTPException(
                status_code=404,
                detail="Surcharge penalty type not found or disabled",
            )
        surcharge_record = PenaltyRecord(
            member_id=application.member_id,
            penalty_type_id=surcharge_type.id,
            status=PenaltyRecordStatus.PENDING.value,
            created_by=current_user.id,
            notes=f"Auto-issued at loan disbursement (loan {str(loan.id)[:8]}, K{application.amount})",
        )
        db.add(surcharge_record)
        db.commit()
        db.refresh(surcharge_record)
        surcharge_record_id = str(surcharge_record.id)
        surcharge_name = surcharge_type.name

    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Loan approved & disbursed",
        details=(
            f"member={_loan_name}, amount=K {application.amount}"
            + (f", surcharge={surcharge_name}" if surcharge_name else "")
        ),
    )
    return {
        "message": "Loan approved, disbursed, and posted to member's account successfully",
        "loan_id": str(loan.id),
        "application_id": str(application.id),
        "surcharge_penalty_id": surcharge_record_id,
        "surcharge_penalty_name": surcharge_name,
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


class BackfillLoanRequest(BaseModel):
    """Body for recording a historical (off-system) loan.

    Used by the treasurer on the Reports → Loans view to onboard loans that
    were disbursed to members outside the app, so their existing repayment
    declarations can be reconciled against a real Loan row.
    """
    member_id: str
    cycle_id: str
    loan_amount: float
    term_months: str
    percentage_interest: float
    disbursement_date: str            # YYYY-MM-DD, must not be in the future
    reason: str                       # audit trail — required
    force: Optional[bool] = False     # bypass one-active-loan rule for genuine multi-loan history


@router.post("/loans/backfill")
def post_backfill_loan(
    body: BackfillLoanRequest,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Record a historical loan (application + immediate disbursement in one call).

    The loan lands with status OPEN, dated on the supplied disbursement_date,
    with the treasurer's free-form interest rate. This lets the Reconciliation
    panel then reallocate existing repayment declarations against the new
    Loan row.
    """
    from app.services.loan_repair import create_backfill_loan
    from app.core.audit import write_audit_log
    from decimal import Decimal
    try:
        member_uuid = UUID(body.member_id)
        cycle_uuid = UUID(body.cycle_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid member_id or cycle_id")

    try:
        result = create_backfill_loan(
            db=db,
            member_id=member_uuid,
            cycle_id=cycle_uuid,
            loan_amount=Decimal(str(body.loan_amount)),
            term_months=body.term_months,
            percentage_interest=Decimal(str(body.percentage_interest)),
            disbursement_date=body.disbursement_date,
            reason=body.reason,
            user_id=current_user.id,
            force=bool(body.force),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Loan backfilled (historical)",
        details=(
            f"member={body.member_id} amount=K{body.loan_amount} "
            f"rate={body.percentage_interest}% term={body.term_months}mo "
            f"disbursed={body.disbursement_date}"
        ),
    )
    return result


class MoveLoanDisbursementRequest(BaseModel):
    """Body for moving a loan's disbursement date to a different month.

    Used when a loan was posted against the wrong month; also re-buckets the
    disbursement JE's dealing_month so the Loan/Revenue report groups the
    loan under the correct period.
    """
    new_disbursement_date: str        # YYYY-MM-DD, must not be in the future
    reason: str


@router.post("/loans/{loan_id}/move-disbursement-date")
def post_move_loan_disbursement_date(
    loan_id: str,
    body: MoveLoanDisbursementRequest,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Move a loan's disbursement date (and dealing month) to the correct
    period. Rejects future dates. Repayment dates on the loan are NOT
    touched — those reflect when payments actually landed."""
    from app.services.loan_repair import edit_loan_disbursement_date
    from app.core.audit import write_audit_log
    try:
        loan_uuid = UUID(loan_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid loan ID")

    try:
        result = edit_loan_disbursement_date(
            db=db,
            loan_id=loan_uuid,
            new_disbursement_date=body.new_disbursement_date,
            reason=body.reason,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Loan disbursement date moved",
        details=(
            f"loan={loan_id} old={result.get('old_disbursement_date')} "
            f"new={result.get('new_disbursement_date')}"
        ),
    )
    return result


@router.get("/members/{member_id}/suggested-loan-rate")
def get_suggested_loan_rate(
    member_id: str,
    cycle_id: Optional[str] = None,
    term_months: Optional[str] = None,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Return the credit-rating-driven interest rate the system WOULD apply
    to this member for the given term, plus the member's credit rating
    context (tier name, borrowing multiplier, max amount). Purely
    informational — treasurer can still type any rate on the backfill
    modal; nothing here is enforced.
    """
    from app.models.policy import (
        MemberCreditRating, CreditRatingInterestRange,
        CreditRatingTier, BorrowingLimitPolicy,
    )
    from app.models.cycle import Cycle
    try:
        member_uuid = UUID(member_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid member ID")

    cycle_uuid = None
    if cycle_id:
        try:
            cycle_uuid = UUID(cycle_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid cycle ID")
    else:
        active = db.query(Cycle).filter(Cycle.status == "active").first()
        if active:
            cycle_uuid = active.id

    empty = {
        "rate": None,
        "reason": None,
        "credit_rating": None,
    }
    if not cycle_uuid:
        return {**empty, "reason": "no active cycle"}

    rating = db.query(MemberCreditRating).filter(
        MemberCreditRating.member_id == member_uuid,
        MemberCreditRating.cycle_id == cycle_uuid,
    ).first()
    if not rating:
        return {**empty, "reason": "no credit rating for this member in this cycle"}

    # Enrich with tier metadata + latest borrowing limit for the tier.
    tier = db.query(CreditRatingTier).filter(CreditRatingTier.id == rating.tier_id).first()
    limit = (
        db.query(BorrowingLimitPolicy)
        .filter(BorrowingLimitPolicy.tier_id == rating.tier_id)
        .order_by(BorrowingLimitPolicy.effective_from.desc())
        .first()
    )
    credit_rating = {
        "tier_id": str(rating.tier_id),
        "tier_name": tier.tier_name if tier else None,
        "tier_order": tier.tier_order if tier else None,
        "tier_description": tier.description if tier else None,
        "multiplier": float(limit.multiplier) if limit and limit.multiplier is not None else None,
        "max_amount": float(limit.max_amount) if limit and limit.max_amount is not None else None,
        "assigned_at": rating.assigned_at.isoformat() if getattr(rating, "assigned_at", None) else None,
    }

    q = db.query(CreditRatingInterestRange).filter(
        CreditRatingInterestRange.tier_id == rating.tier_id,
        CreditRatingInterestRange.cycle_id == cycle_uuid,
    )
    if term_months:
        rng = q.filter(
            (CreditRatingInterestRange.term_months == term_months)
            | (CreditRatingInterestRange.term_months.is_(None))
        ).first()
    else:
        rng = q.first()
    if not rng:
        return {
            "rate": None,
            "reason": "no interest range configured for this term/tier",
            "credit_rating": credit_rating,
        }
    return {
        "rate": float(rng.effective_rate_percent),
        "reason": "from credit rating × term",
        "credit_rating": credit_rating,
    }


class ReconcileDeclarationRequest(BaseModel):
    """Body for creating or editing a member's declaration on behalf.

    Handles three cases in one call:
      * declaration missing  → create + auto-post (posts full JE)
      * declaration PENDING  → update amounts + auto-post
      * declaration APPROVED → per-category correcting JE for deltas
    """
    member_id: str
    month: str                           # YYYY-MM-DD (first of the effective month)
    savings_amount: float = 0.0
    social_fund: float = 0.0
    admin_fund: float = 0.0
    penalties: float = 0.0
    interest_on_loan: float = 0.0
    loan_repayment: float = 0.0
    reason: str


@router.post("/declarations/reconcile-post")
def post_reconcile_declaration(
    body: ReconcileDeclarationRequest,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Create, edit, or correct a member's monthly declaration in one call.

    Behaviour depends on the declaration's current state (looked up by
    member × effective month):

    * **No declaration** → creates the Declaration with the supplied amounts,
      creates a synthetic DepositProof (upload_path="reconciliation"), runs
      the standard `approve_deposit` service so the JE, per-category
      accounts, Repayment row, and penalty matches all post as usual.
    * **PENDING / PROOF** → updates the declared amounts and re-runs
      `approve_deposit` so the deposit is approved with the corrected
      figures. If a real DepositProof was uploaded already it's reused.
    * **APPROVED** → posts a single per-category correcting JE (source_type
      `"declaration_edit"`) with Dr/Cr Bank Cash ↔ each changed account for
      the delta amount; updates the Declaration row; syncs the linked
      Repayment principal/interest if either loan-side amount changed.

    Rejects future months and empty (all-zero) submissions.
    """
    from app.services.transaction_repair import reconcile_declaration_and_post
    from app.core.audit import write_audit_log
    from decimal import Decimal
    from datetime import date as _date
    try:
        member_uuid = UUID(body.member_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid member_id")
    try:
        month = _date.fromisoformat(body.month[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid month (use YYYY-MM-DD)")
    try:
        result = reconcile_declaration_and_post(
            db=db,
            member_id=member_uuid,
            month=month,
            savings=Decimal(str(body.savings_amount)),
            social_fund=Decimal(str(body.social_fund)),
            admin_fund=Decimal(str(body.admin_fund)),
            penalties=Decimal(str(body.penalties)),
            interest_on_loan=Decimal(str(body.interest_on_loan)),
            loan_repayment=Decimal(str(body.loan_repayment)),
            reason=body.reason,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action=f"Declaration reconciled ({result.get('outcome')})",
        details=(
            f"member={body.member_id} month={body.month} "
            f"S={body.savings_amount} SF={body.social_fund} AF={body.admin_fund} "
            f"P={body.penalties} I={body.interest_on_loan} LR={body.loan_repayment}"
        ),
    )
    return result


class PostRepaymentForDeclarationRequest(BaseModel):
    """Post a fresh Repayment against a chosen loan for a declaration that
    has non-zero loan_repayment / interest but no attributed Repayment row.

    Happens with historical declarations reconciled off-system, or when the
    active-loan lookup returned nothing at the time of approval and a loan
    has since been backfilled. Amounts must not exceed what the declaration
    committed.
    """
    loan_id: str
    principal: float
    interest: float
    reason: str


@router.post("/declarations/{declaration_id}/post-repayment")
def post_repayment_for_declaration(
    declaration_id: str,
    body: PostRepaymentForDeclarationRequest,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Create a Repayment row against a chosen loan for a declaration whose
    loan_repayment / interest never attached to a loan at approval time.

    The org-level ledger is already balanced from the deposit approval JE
    (which credited LOANS_RECEIVABLE / INTEREST_RECEIVABLE at that time).
    This endpoint only creates a per-loan attribution row — it does NOT
    move any additional cash. A balanced no-op JE is posted to satisfy the
    Repayment.journal_entry_id FK and to leave a full audit trail.
    """
    from app.models.transaction import Repayment
    from app.models.ledger import LedgerAccount
    from app.services.accounting import create_journal_entry, get_dealing_month_date
    from app.core.audit import write_audit_log
    from decimal import Decimal
    import uuid as _uuid

    try:
        decl_uuid = UUID(declaration_id)
        loan_uuid = UUID(body.loan_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid declaration_id or loan_id")

    principal = Decimal(str(body.principal or 0)).quantize(Decimal("0.01"))
    interest = Decimal(str(body.interest or 0)).quantize(Decimal("0.01"))
    if principal < 0 or interest < 0:
        raise HTTPException(status_code=400, detail="Amounts cannot be negative")
    if principal == 0 and interest == 0:
        raise HTTPException(status_code=400, detail="Provide a principal or interest amount")

    reason = (body.reason or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Reason (min 5 chars) required for audit")

    declaration = db.query(Declaration).filter(Declaration.id == decl_uuid).first()
    if not declaration:
        raise HTTPException(status_code=404, detail="Declaration not found")

    loan = db.query(Loan).filter(Loan.id == loan_uuid).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.member_id != declaration.member_id:
        raise HTTPException(status_code=400, detail="Loan belongs to a different member")

    # Guard: amounts must not exceed what the declaration committed. Prevents
    # accidentally over-posting more than the member paid.
    declared_repay = Decimal(str(declaration.declared_loan_repayment or 0))
    declared_interest = Decimal(str(declaration.declared_interest_on_loan or 0))
    if principal > declared_repay + Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Principal (K{principal}) exceeds declared loan repayment (K{declared_repay})",
        )
    if interest > declared_interest + Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Interest (K{interest}) exceeds declared interest (K{declared_interest})",
        )

    # Sum of any existing live Repayment attributions on this declaration.
    # The new attribution must not push totals over what was declared.
    from app.models.ledger import JournalEntry as _JE
    deposit_proof = db.query(DepositProof).filter(
        DepositProof.declaration_id == declaration.id
    ).order_by(DepositProof.uploaded_at.desc()).first()
    approval_je_id = None
    if deposit_proof:
        approval = db.query(DepositApproval).filter(
            DepositApproval.deposit_proof_id == deposit_proof.id
        ).first()
        if approval and approval.journal_entry_id:
            approval_je_id = approval.journal_entry_id
    already_p = Decimal("0.00")
    already_i = Decimal("0.00")
    if approval_je_id:
        existing_reps = db.query(Repayment).filter(
            Repayment.journal_entry_id == approval_je_id
        ).all()
        for r in existing_reps:
            je = db.query(_JE).filter(_JE.id == r.journal_entry_id).first()
            if je and je.reversed_by is None and je.reversed_at is None:
                already_p += Decimal(str(r.principal_amount or 0))
                already_i += Decimal(str(r.interest_amount or 0))
    # Also count carve-out reps that reference this declaration (edge case,
    # ignored — carve-outs are per-loan reallocations, not new attributions).

    if already_p + principal > declared_repay + Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Adding K{principal} principal would exceed declared repayment (already attributed K{already_p} of K{declared_repay})",
        )
    if already_i + interest > declared_interest + Decimal("0.01"):
        raise HTTPException(
            status_code=400,
            detail=f"Adding K{interest} interest would exceed declared interest (already attributed K{already_i} of K{declared_interest})",
        )

    # Balanced no-op JE that documents the attribution. Same pattern as the
    # move-repayment carve-out: self-cancelling Dr/Cr on each account so
    # org-level ledger totals don't move (they already posted at approval).
    loans_rec = db.query(LedgerAccount).filter(
        LedgerAccount.account_code.like("LOANS_RECEIVABLE%")
    ).first()
    int_inc = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_INCOME"
    ).first()
    if principal > 0 and not loans_rec:
        raise HTTPException(status_code=500, detail="LOANS_RECEIVABLE account missing")
    if interest > 0 and not int_inc:
        raise HTTPException(status_code=500, detail="INTEREST_INCOME account missing")

    lines: list = []
    if principal > 0:
        lines += [
            {"account_id": loans_rec.id, "debit_amount": principal,
             "credit_amount": Decimal("0.00"),
             "description": f"Attribute repayment principal to loan {str(loan.id)[:8]}"},
            {"account_id": loans_rec.id, "debit_amount": Decimal("0.00"),
             "credit_amount": principal,
             "description": f"Attribute from declaration {str(declaration.id)[:8]}"},
        ]
    if interest > 0:
        lines += [
            {"account_id": int_inc.id, "debit_amount": interest,
             "credit_amount": Decimal("0.00"),
             "description": f"Attribute repayment interest to loan {str(loan.id)[:8]}"},
            {"account_id": int_inc.id, "debit_amount": Decimal("0.00"),
             "credit_amount": interest,
             "description": f"Attribute from declaration {str(declaration.id)[:8]}"},
        ]

    new_rep_id = _uuid.uuid4()
    attach_je = create_journal_entry(
        db=db,
        description=(
            f"Repayment attribution — decl {str(declaration.id)[:8]} → loan {str(loan.id)[:8]} "
            f"(P={principal} I={interest}). Reason: {reason}"
        )[:255],
        lines=lines,
        dealing_month=get_dealing_month_date(db, loan.cycle_id, declaration.effective_month),
        cycle_id=loan.cycle_id,
        source_type="repayment_attribution",
        source_ref=str(new_rep_id),
        created_by=current_user.id,
    )

    new_rep = Repayment(
        id=new_rep_id,
        loan_id=loan.id,
        repayment_date=declaration.effective_month,
        principal_amount=principal,
        interest_amount=interest,
        total_amount=principal + interest,
        journal_entry_id=attach_je.id,
    )
    db.add(new_rep)
    db.commit()
    db.refresh(new_rep)

    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Repayment posted from declaration",
        details=(
            f"declaration={declaration_id} loan={body.loan_id} "
            f"P={principal} I={interest}"
        ),
    )
    return {
        "repayment_id": str(new_rep.id),
        "loan_id": str(loan.id),
        "principal": float(principal),
        "interest": float(interest),
        "total": float(principal + interest),
        "reason": reason,
    }


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

        member_name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip()
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

        # Calculate total declaration amount.
        # A declaration with total == 0 but status APPROVED is a "phantom" caused
        # by an old empty reconciliation; surface it (declaration_amount=0,
        # is_phantom=True) so the treasurer can spot and reject it instead of
        # hiding the row entirely.
        declaration_amount = None
        total = Decimal("0.00")
        if declaration:
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
            if total > 0:
                declaration_amount = float(total)

        # Check if deposit proof is approved (paid)
        is_paid = False
        if declaration:
            deposit_proof = db.query(DepositProof).filter(
                DepositProof.declaration_id == declaration.id,
                DepositProof.status == DepositProofStatus.APPROVED.value
            ).first()
            is_paid = deposit_proof is not None

        is_phantom = bool(declaration and is_paid and total == 0)
        if is_phantom and declaration_amount is None:
            declaration_amount = 0.0

        # Provenance flags so the report can render small badges next to each
        # member's amount and the treasurer knows at a glance whether the
        # entry came from a real upload, was created via reconciliation, or
        # was approved purely via reconciliation. Mirrors the same fields on
        # the member's declarations endpoint.
        has_real_proof = False
        created_via_reconciliation = False
        approved_via_reconciliation = False
        if declaration:
            all_proofs = db.query(DepositProof).filter(
                DepositProof.declaration_id == declaration.id
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
                is_paid
                and not has_real_proof
                and any(
                    p.upload_path == "reconciliation"
                    and p.status == DepositProofStatus.APPROVED.value
                    for p in all_proofs
                )
            )

        # Include ALL members (with or without declarations)
        result.append({
            "member_id": str(member.id),
            "member_name": member_name,
            "declaration_id": str(declaration.id) if declaration else None,
            "declaration_amount": declaration_amount,
            "is_paid": is_paid,
            "is_phantom": is_phantom,
            "has_real_proof": has_real_proof,
            "created_via_reconciliation": created_via_reconciliation,
            "approved_via_reconciliation": approved_via_reconciliation,
        })
    
    # Sort by surname (last word of name)
    result.sort(key=lambda x: (x["member_name"].rsplit(" ", 1)[-1].lower(), x["member_name"].rsplit(" ", 1)[0].lower()))

    total_declared = sum(m["declaration_amount"] or 0 for m in result)
    total_deposited = sum(m["declaration_amount"] or 0 for m in result if m["is_paid"])

    return {
        "month": target_date.isoformat(),
        "members": result,
        "total_declared": total_declared,
        "total_deposited": total_deposited,
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
    member_name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip() or "Unknown"

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

    # Resolve which loan(s) this declaration's loan_repayment + interest was
    # attributed to — the Repayment rows share the deposit-approval JE via
    # `Repayment.journal_entry_id`. Also fetch the member's full loan list
    # so the treasurer can reassign to a different loan when the auto-attach
    # picked wrong.
    from app.models.transaction import Repayment
    from app.models.ledger import JournalEntry
    from app.services.loan_repair import loan_has_live_disbursement

    repayments_attributed: list[dict] = []
    approval_je_ids: list = []
    if deposit_proof:
        approval = db.query(DepositApproval).filter(
            DepositApproval.deposit_proof_id == deposit_proof.id
        ).first()
        if approval and approval.journal_entry_id:
            approval_je_ids.append(approval.journal_entry_id)

    def _loan_label(loan) -> str:
        short = str(loan.id)[:8]
        if loan.disbursement_date:
            return f"{loan.disbursement_date.strftime('%B %Y')} ({short})"
        return f"Undisbursed ({short})"

    if approval_je_ids:
        reps = db.query(Repayment).filter(
            Repayment.journal_entry_id.in_(approval_je_ids)
        ).all()
        for rep in reps:
            rep_je = db.query(JournalEntry).filter(JournalEntry.id == rep.journal_entry_id).first()
            is_live = bool(rep_je and rep_je.reversed_by is None and rep_je.reversed_at is None)
            rep_loan = db.query(Loan).filter(Loan.id == rep.loan_id).first()
            repayments_attributed.append({
                "id": str(rep.id),
                "loan_id": str(rep.loan_id),
                "loan_label": _loan_label(rep_loan) if rep_loan else str(rep.loan_id)[:8],
                "principal": float(rep.principal_amount or 0),
                "interest": float(rep.interest_amount or 0),
                "total": float(rep.total_amount or 0),
                "repayment_date": rep.repayment_date.isoformat() if rep.repayment_date else None,
                "is_live": is_live,
            })

    # All of the member's loans (for the "Change loan" / "Post repayment"
    # pickers). Ordered by disbursement date ascending so the picker reads
    # chronologically. `is_live_disbursement` = has an un-reversed
    # disbursement JE — reversed ones are shown but disabled in the UI.
    member_loans_list: list[dict] = []
    all_loans = (
        db.query(Loan)
        .filter(Loan.member_id == member_uuid)
        .order_by(Loan.disbursement_date.asc())
        .all()
    )
    # Push undisbursed loans (disbursement_date IS NULL) to the end of the
    # list — MySQL sorts NULL first in ASC, but for the picker chronological
    # reading with unknowns at the bottom is more useful.
    all_loans = sorted(all_loans, key=lambda L: (L.disbursement_date is None, L.disbursement_date or 0))
    for L in all_loans:
        member_loans_list.append({
            "id": str(L.id),
            "label": _loan_label(L),
            "disbursement_date": L.disbursement_date.isoformat() if L.disbursement_date else None,
            "loan_amount": float(L.loan_amount or 0),
            "percentage_interest": float(L.percentage_interest or 0),
            "loan_status": L.loan_status.value if L.loan_status else None,
            "is_live_disbursement": loan_has_live_disbursement(db, L.id),
        })

    declared_repay = float(declaration.declared_loan_repayment or 0)
    declared_interest = float(declaration.declared_interest_on_loan or 0)
    has_orphan_repayment = (
        (declared_repay > 0 or declared_interest > 0)
        and len([r for r in repayments_attributed if r["is_live"]]) == 0
    )

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
            "upload_path": deposit_proof.upload_path,
            # Convenience flag for the UI: true when there's a real uploaded
            # file (not the "reconciliation" placeholder and not empty).
            "has_file": bool(
                deposit_proof.upload_path
                and deposit_proof.upload_path != "reconciliation"
            ),
        } if deposit_proof else None,
        "repayments_attributed": repayments_attributed,
        "member_loans": member_loans_list,
        "has_orphan_repayment": has_orphan_repayment,
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

    # Query every loan disbursed in the target month, regardless of current
    # status. "Loans disbursed this month" means the borrowing that actually
    # happened in that period — a loan that was borrowed AND fully repaid in
    # the same month is still December-2025 borrowing activity and must show
    # up in December's report. Excluding CLOSED (or PENDING loans that were
    # backfilled via reconciliation and immediately paid off) silently hid
    # historical loans reconciled off-system.
    #
    # The `loan_has_live_disbursement` check remains the semantic gate: any
    # loan whose disbursement JE has been reversed is genuinely no longer a
    # disbursement and drops out.
    from app.services.loan_repair import loan_has_live_disbursement
    loans = db.query(Loan).filter(
        extract("year", Loan.disbursement_date) == target_year,
        extract("month", Loan.disbursement_date) == target_month,
    ).order_by(Loan.disbursement_date.asc()).all()
    loans = [L for L in loans if loan_has_live_disbursement(db, L.id)]

    # Track member IDs that already have disbursed loans to avoid duplicates
    disbursed_member_ids = set()

    result = []
    for loan in loans:
        member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
        user = db.query(UserModel).filter(UserModel.id == member.user_id).first() if member else None
        if not user:
            continue

        member_name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip()
        if not member_name:
            continue

        disbursed_member_ids.add(loan.member_id)
        result.append({
            "loan_id": str(loan.id),
            "member_id": str(loan.member_id),
            "member_name": member_name,
            "loan_amount": float(loan.loan_amount),
            "is_approved": True,
            "is_disbursed": True,
            "is_paid": True,
        })

    # Also include pending loan applications for the target month that haven't been disbursed yet
    pending_apps = db.query(LoanApplication).filter(
        LoanApplication.status == LoanApplicationStatus.PENDING,
        extract("year", LoanApplication.application_date) == target_year,
        extract("month", LoanApplication.application_date) == target_month,
    ).order_by(LoanApplication.application_date.asc()).all()

    for app in pending_apps:
        # Skip if this member already has a disbursed loan this month
        if app.member_id in disbursed_member_ids:
            continue

        member = db.query(MemberProfile).filter(MemberProfile.id == app.member_id).first()
        user = db.query(UserModel).filter(UserModel.id == member.user_id).first() if member else None
        if not user:
            continue

        member_name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip()
        if not member_name:
            continue

        result.append({
            "loan_id": str(app.id),
            "member_id": str(app.member_id),
            "member_name": member_name,
            "loan_amount": float(app.amount),
            "is_approved": False,
            "is_disbursed": False,
            "is_paid": False,
        })

    result.sort(key=lambda x: (x["member_name"].rsplit(" ", 1)[-1].lower(), x["member_name"].rsplit(" ", 1)[0].lower()))

    total_applied = sum(item["loan_amount"] for item in result)
    total_disbursed = sum(item["loan_amount"] for item in result if item["is_disbursed"])

    return {
        "loans": result,
        "total_applied": total_applied,
        "total_disbursed": total_disbursed,
    }


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

        # Clean up the previous file so we don't accumulate orphans on disk
        # whenever a treasurer/chairman corrects a mistaken upload.
        old_path = stmt.upload_path
        if old_path:
            try:
                import os
                if os.path.isfile(old_path) and old_path != str(file_path):
                    os.remove(old_path)
            except OSError:
                pass

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


# ---------------------------------------------------------------------------
# Scheduler control endpoints
# ---------------------------------------------------------------------------

class SchedulerIntervalUpdate(BaseModel):
    interval_minutes: int


@router.get("/scheduler/status")
def scheduler_status(
    current_user: User = Depends(require_treasurer),
):
    """Return the current state of the background scheduler."""
    from app.services.scheduler import get_scheduler_status
    return get_scheduler_status()


@router.put("/scheduler/interval")
def update_scheduler_interval(
    body: SchedulerIntervalUpdate,
    current_user: User = Depends(require_treasurer),
):
    """Change the scheduler run interval (in minutes) at runtime."""
    if body.interval_minutes < 1:
        raise HTTPException(status_code=400, detail="Interval must be at least 1 minute")

    from app.services.scheduler import reschedule_jobs, get_scheduler_status
    try:
        reschedule_jobs(body.interval_minutes)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    from app.core.audit import write_audit_log
    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role=current_user.role.value if current_user.role else "treasurer",
        action="Scheduler interval updated",
        details=f"new_interval={body.interval_minutes} minutes",
    )

    return get_scheduler_status()


# ---------------------------------------------------------------------------
# Penalty Reversals — Treasurer approves reversal requests from Compliance
# ---------------------------------------------------------------------------

@router.get("/penalties/pending-reversals")
def get_pending_reversals(
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Get penalties awaiting reversal approval."""
    from app.models.transaction import PenaltyRecordStatus
    penalties = db.query(PenaltyRecord).filter(
        PenaltyRecord.status == PenaltyRecordStatus.REVERSAL_PENDING.value
    ).order_by(PenaltyRecord.reversal_requested_at.desc()).all()

    result = []
    for p in penalties:
        member = p.member
        user = db.query(User).filter(User.id == member.user_id).first() if member else None
        member_name = f"{(user.first_name or '')} {(user.last_name or '')}".strip() if user else "Unknown"
        requester = db.query(User).filter(User.id == p.reversal_requested_by).first() if p.reversal_requested_by else None
        result.append({
            "id": str(p.id),
            "member_name": member_name,
            "penalty_type_name": p.penalty_type.name if p.penalty_type else "Unknown",
            "fee_amount": float(p.penalty_type.fee_amount) if p.penalty_type else 0,
            "date_issued": p.date_issued.isoformat() if p.date_issued else None,
            "notes": p.notes,
            "reversal_reason": p.reversal_reason,
            "reversal_requested_by_name": f"{(requester.first_name or '')} {(requester.last_name or '')}".strip() if requester else None,
            "reversal_requested_at": p.reversal_requested_at.isoformat() if p.reversal_requested_at else None,
        })
    return result


@router.post("/penalties/{penalty_id}/approve-reversal")
def approve_penalty_reversal(
    penalty_id: str,
    current_user: User = Depends(require_treasurer),
    db: Session = Depends(get_db),
):
    """Approve a penalty reversal — creates a reversing journal entry and marks
    the penalty as REVERSED. The penalty no longer appears in declarations."""
    from app.models.transaction import PenaltyRecordStatus
    from app.models.ledger import JournalEntry, JournalLine
    from app.services.accounting import create_journal_entry
    from app.core.audit import write_audit_log

    try:
        pid = UUID(penalty_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid penalty ID")

    penalty = db.query(PenaltyRecord).filter(PenaltyRecord.id == pid).first()
    if not penalty:
        raise HTTPException(status_code=404, detail="Penalty not found")

    status_val = penalty.status.value if isinstance(penalty.status, PenaltyRecordStatus) else penalty.status
    if status_val != PenaltyRecordStatus.REVERSAL_PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Penalty is not pending reversal. Current status: {status_val}",
        )

    # Create a reversing journal entry if the original penalty had one.
    # Original: Debit MEM_SAV (reduce savings), Credit PENALTY_INCOME
    # Reversal: Debit PENALTY_INCOME, Credit MEM_SAV (restore savings)
    reversal_je = None
    if penalty.journal_entry_id:
        original_je = db.query(JournalEntry).filter(JournalEntry.id == penalty.journal_entry_id).first()
        if original_je and not original_je.reversed_by:
            original_lines = db.query(JournalLine).filter(
                JournalLine.journal_entry_id == original_je.id
            ).all()

            reversal_lines = []
            for line in original_lines:
                reversal_lines.append({
                    "account_id": line.ledger_account_id,
                    "debit_amount": line.credit_amount,
                    "credit_amount": line.debit_amount,
                    "description": f"Reversal: {line.description or ''}",
                })

            member = penalty.member
            user = db.query(User).filter(User.id == member.user_id).first() if member else None
            member_name = f"{(user.first_name or '')} {(user.last_name or '')}".strip() if user else "Unknown"

            reversal_je = create_journal_entry(
                db=db,
                description=f"Penalty reversal: {penalty.penalty_type.name if penalty.penalty_type else 'Unknown'} — {member_name} — {penalty.reversal_reason or ''}",
                lines=reversal_lines,
                dealing_month=original_je.dealing_month,
                cycle_id=original_je.cycle_id,
                source_ref=str(penalty.id),
                source_type="penalty_reversal",
                created_by=current_user.id,
            )

            original_je.reversed_by = current_user.id
            original_je.reversed_at = datetime.utcnow()
            original_je.reversal_reason = penalty.reversal_reason

    penalty.status = PenaltyRecordStatus.REVERSED
    penalty.reversed_by = current_user.id
    penalty.reversed_at = datetime.utcnow()
    if reversal_je:
        penalty.reversal_journal_entry_id = reversal_je.id
    db.commit()

    member = penalty.member
    user = db.query(User).filter(User.id == member.user_id).first() if member else None
    member_name = f"{(user.first_name or '')} {(user.last_name or '')}".strip() if user else "Unknown"

    write_audit_log(
        user_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
        user_role="treasurer",
        action="Penalty reversal approved",
        details=f"member={member_name}, penalty={penalty.penalty_type.name if penalty.penalty_type else 'Unknown'}, reason={penalty.reversal_reason or 'N/A'}",
    )

    return {"message": "Penalty reversed successfully", "penalty_id": str(penalty.id)}
