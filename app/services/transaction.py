from sqlalchemy.orm import Session
from app.models.transaction import (
    Declaration,
    DeclarationStatus,
    DepositProof,
    DepositProofStatus,
    DepositApproval,
    LoanApplication,
    LoanApplicationStatus,
    Loan,
    LoanStatus,
    Repayment,
    PenaltyRecord,
    PenaltyRecordStatus,
    PenaltyType
)
from app.models.ledger import LedgerAccount, AccountType
from app.services.accounting import create_journal_entry, get_account_balance
from app.models.member import MemberProfile
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime
from typing import Optional


def create_declaration(
    db: Session,
    member_id: UUID,
    cycle_id: UUID,
    effective_month: date,
    declared_savings_amount: Decimal = None,
    declared_social_fund: Decimal = None,
    declared_admin_fund: Decimal = None,
    declared_penalties: Decimal = None,
    declared_interest_on_loan: Decimal = None,
    declared_loan_repayment: Decimal = None
) -> Declaration:
    """
    Create a member declaration.
    
    Validates that no declaration exists for the same member, cycle, and month.
    """
    from sqlalchemy import and_, extract
    
    # Check if declaration already exists for this member, cycle, and month
    existing = db.query(Declaration).filter(
        and_(
            Declaration.member_id == member_id,
            Declaration.cycle_id == cycle_id,
            extract('year', Declaration.effective_month) == effective_month.year,
            extract('month', Declaration.effective_month) == effective_month.month
        )
    ).first()
    
    if existing:
        raise ValueError(f"Declaration already exists for {effective_month.strftime('%B %Y')}")
    
    declaration = Declaration(
        member_id=member_id,
        cycle_id=cycle_id,
        effective_month=effective_month,
        declared_savings_amount=declared_savings_amount,
        declared_social_fund=declared_social_fund,
        declared_admin_fund=declared_admin_fund,
        declared_penalties=declared_penalties,
        declared_interest_on_loan=declared_interest_on_loan,
        declared_loan_repayment=declared_loan_repayment,
        status=DeclarationStatus.PENDING
    )
    db.add(declaration)
    db.flush()  # Flush to get declaration ID, but don't commit yet
    
    # Check if this is the member's first declaration for this cycle
    # If so, post initial required amounts for Social Fund and Admin Fund
    other_declarations = db.query(Declaration).filter(
        Declaration.member_id == member_id,
        Declaration.cycle_id == cycle_id,
        Declaration.id != declaration.id
    ).first()
    
    is_first_declaration = other_declarations is None
    
    if is_first_declaration:
        # Get the cycle to check for required amounts
        from app.models.cycle import Cycle
        cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
        
        if cycle and (cycle.social_fund_required or cycle.admin_fund_required):
            # Get or create member's Social Fund and Admin Fund accounts
            from app.models.ledger import LedgerAccount, AccountType
            from app.services.accounting import create_journal_entry
            
            # Get or create organization-level receivable accounts (for contra entries)
            social_fund_receivable = db.query(LedgerAccount).filter(
                LedgerAccount.account_code == "SOC_FUND_REC"
            ).first()
            
            if not social_fund_receivable:
                social_fund_receivable = LedgerAccount(
                    account_code="SOC_FUND_REC",
                    account_name="Social Fund Receivable",
                    account_type=AccountType.ASSET,
                    description="Social fund receivables from members (contra account for member social fund accounts)"
                )
                db.add(social_fund_receivable)
                db.flush()
            
            admin_fund_receivable = db.query(LedgerAccount).filter(
                LedgerAccount.account_code == "ADM_FUND_REC"
            ).first()
            
            if not admin_fund_receivable:
                admin_fund_receivable = LedgerAccount(
                    account_code="ADM_FUND_REC",
                    account_name="Admin Fund Receivable",
                    account_type=AccountType.ASSET,
                    description="Admin fund receivables from members (contra account for member admin fund accounts)"
                )
                db.add(admin_fund_receivable)
                db.flush()
            
            # Get or create member's Social Fund account
            member_social_fund = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_id,
                LedgerAccount.account_name.ilike("%social fund%")
            ).first()
            
            if not member_social_fund:
                short_id = str(member_id).replace('-', '')[:8]
                member_social_fund = LedgerAccount(
                    account_code=f"MEM_SOC_{short_id}",
                    account_name=f"Social Fund - {member_id}",
                    account_type=AccountType.ASSET,
                    member_id=member_id,
                    description=f"Social fund receivable account for member {member_id}"
                )
                db.add(member_social_fund)
                db.flush()
            
            # Get or create member's Admin Fund account
            member_admin_fund = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == member_id,
                LedgerAccount.account_name.ilike("%admin fund%")
            ).first()
            
            if not member_admin_fund:
                short_id = str(member_id).replace('-', '')[:8]
                member_admin_fund = LedgerAccount(
                    account_code=f"MEM_ADM_{short_id}",
                    account_name=f"Admin Fund - {member_id}",
                    account_type=AccountType.ASSET,
                    member_id=member_id,
                    description=f"Admin fund receivable account for member {member_id}"
                )
                db.add(member_admin_fund)
                db.flush()
            
            # Check if initial debits already exist for this cycle (prevent duplicates)
            from app.models.ledger import JournalEntry, JournalLine
            existing_initial = db.query(JournalEntry).join(JournalLine).filter(
                JournalEntry.cycle_id == cycle_id,
                JournalEntry.source_type == "cycle_initial_requirement",
                JournalLine.ledger_account_id.in_([member_social_fund.id, member_admin_fund.id])
            ).first()
            
            if not existing_initial:
                # Create journal entry for initial required amounts
                journal_lines = []
                
                if cycle.social_fund_required and cycle.social_fund_required > 0:
                    # Post initial required amount as debit to member account
                    journal_lines.append({
                        "account_id": member_social_fund.id,
                        "debit_amount": cycle.social_fund_required,
                        "credit_amount": Decimal("0.00"),
                        "description": f"Initial required amount for {cycle.year} - Social Fund"
                    })
                    # Credit organization receivable to balance
                    journal_lines.append({
                        "account_id": social_fund_receivable.id,
                        "debit_amount": Decimal("0.00"),
                        "credit_amount": cycle.social_fund_required,
                        "description": f"Initial required amount for {cycle.year} - Social Fund (contra)"
                    })
                
                if cycle.admin_fund_required and cycle.admin_fund_required > 0:
                    # Post initial required amount as debit to member account
                    journal_lines.append({
                        "account_id": member_admin_fund.id,
                        "debit_amount": cycle.admin_fund_required,
                        "credit_amount": Decimal("0.00"),
                        "description": f"Initial required amount for {cycle.year} - Admin Fund"
                    })
                    # Credit organization receivable to balance
                    journal_lines.append({
                        "account_id": admin_fund_receivable.id,
                        "debit_amount": Decimal("0.00"),
                        "credit_amount": cycle.admin_fund_required,
                        "description": f"Initial required amount for {cycle.year} - Admin Fund (contra)"
                    })
                
                if journal_lines:
                    create_journal_entry(
                        db=db,
                        description=f"Initial required amounts for member {member_id} - Cycle {cycle.year}",
                        lines=journal_lines,
                        cycle_id=cycle_id,
                        source_type="cycle_initial_requirement",
                        created_by=None  # System-generated
                    )
    
    db.commit()
    db.refresh(declaration)
    return declaration


def update_declaration(
    db: Session,
    declaration_id: UUID,
    member_id: UUID,
    cycle_id: UUID,
    effective_month: date,
    declared_savings_amount: Decimal = None,
    declared_social_fund: Decimal = None,
    declared_admin_fund: Decimal = None,
    declared_penalties: Decimal = None,
    declared_interest_on_loan: Decimal = None,
    declared_loan_repayment: Decimal = None,
    allow_rejected_edit: bool = False
) -> Declaration:
    """
    Update a declaration.
    
    Only allows updates if:
    1. Current date is before the 20th of the declaration's effective month (unless allow_rejected_edit=True)
    2. Declaration status is PENDING (or APPROVED if allow_rejected_edit=True)
    """
    from datetime import date
    
    declaration = db.query(Declaration).filter(
        Declaration.id == declaration_id,
        Declaration.member_id == member_id
    ).first()
    if not declaration:
        raise ValueError("Declaration not found")
    
    if not allow_rejected_edit:
        # Check if we can still edit (current month only, but no 20th day restriction)
        today = date.today()
        effective_date = declaration.effective_month
        
        # Check if today is after the effective month (cannot edit previous months)
        if today.year > effective_date.year or (today.year == effective_date.year and today.month > effective_date.month):
            raise ValueError("Cannot edit declarations from previous months")
        
        # Allow editing current month declarations anytime (removed 20th day restriction)
        # Only allow editing PENDING declarations
        if declaration.status != DeclarationStatus.PENDING:
            raise ValueError(f"Cannot edit declaration with status: {declaration.status.value}")
    else:
        # When editing after rejection, allow editing even if past 20th, but only if status is PENDING or APPROVED
        if declaration.status not in [DeclarationStatus.PENDING, DeclarationStatus.APPROVED]:
            raise ValueError(f"Cannot edit declaration with status: {declaration.status.value}")
    
    # Update fields
    declaration.cycle_id = cycle_id
    declaration.effective_month = effective_month
    if declared_savings_amount is not None:
        declaration.declared_savings_amount = declared_savings_amount
    if declared_social_fund is not None:
        declaration.declared_social_fund = declared_social_fund
    if declared_admin_fund is not None:
        declaration.declared_admin_fund = declared_admin_fund
    if declared_penalties is not None:
        declaration.declared_penalties = declared_penalties
    if declared_interest_on_loan is not None:
        declaration.declared_interest_on_loan = declared_interest_on_loan
    if declared_loan_repayment is not None:
        declaration.declared_loan_repayment = declared_loan_repayment
    
    # If it was APPROVED (rejected proof), reset to PENDING
    if allow_rejected_edit and declaration.status == DeclarationStatus.APPROVED:
        declaration.status = DeclarationStatus.PENDING
    
    declaration.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(declaration)
    return declaration


def approve_deposit(
    db: Session,
    deposit_proof_id: UUID,
    approved_by: UUID,
    bank_cash_account_id: UUID,
    member_savings_account_id: UUID,
    member_social_fund_account_id: UUID = None,
    member_admin_fund_account_id: UUID = None,
    penalties_payable_account_id: UUID = None,
    interest_income_account_id: UUID = None,
    loans_receivable_account_id: UUID = None
) -> DepositApproval:
    """
    Approve deposit proof and post to ledger.
    
    Uses amounts from the associated declaration to post to correct accounts.
    """
    deposit = db.query(DepositProof).filter(DepositProof.id == deposit_proof_id).first()
    if not deposit:
        raise ValueError("Deposit proof not found")
    
    # Allow approval of both SUBMITTED and REJECTED proofs
    # REJECTED proofs can be approved if treasurer is satisfied with member's response
    if deposit.status not in [DepositProofStatus.SUBMITTED.value, DepositProofStatus.REJECTED.value]:
        raise ValueError(f"Deposit proof cannot be approved. Current status: {deposit.status}")
    
    # Get declaration to use declared amounts
    declaration = None
    if deposit.declaration_id:
        declaration = db.query(Declaration).filter(Declaration.id == deposit.declaration_id).first()
    
    if not declaration:
        raise ValueError("Declaration not found for this deposit proof")
    
    # Get declared amounts (use 0 if not declared)
    savings_amount = declaration.declared_savings_amount or Decimal("0.00")
    social_fund = declaration.declared_social_fund or Decimal("0.00")
    admin_fund = declaration.declared_admin_fund or Decimal("0.00")
    penalties = declaration.declared_penalties or Decimal("0.00")
    interest_on_loan = declaration.declared_interest_on_loan or Decimal("0.00")
    loan_repayment = declaration.declared_loan_repayment or Decimal("0.00")
    
    # Calculate total expected amount
    total_expected = savings_amount + social_fund + admin_fund + penalties + interest_on_loan + loan_repayment
    
    # Verify deposit amount matches declaration total (with small tolerance for rounding)
    if abs(deposit.amount - total_expected) > Decimal("0.01"):
        raise ValueError(
            f"Deposit amount ({deposit.amount}) does not match declaration total ({total_expected})"
        )
    
    # Build journal entry lines
    lines = [
        {
            "account_id": bank_cash_account_id,
            "debit_amount": deposit.amount,
            "credit_amount": Decimal("0.00"),
            "description": f"Bank cash received for declaration {declaration.effective_month}"
        }
    ]
    
    # Credit member savings
    if savings_amount > 0:
        lines.append({
            "account_id": member_savings_account_id,
            "debit_amount": Decimal("0.00"),
            "credit_amount": savings_amount,
            "description": "Member savings deposit"
        })
    
    # Credit member social fund account (reduces outstanding balance)
    # Also debit organization receivable to balance
    if social_fund > 0:
        # Get or create member's social fund account if it doesn't exist
        if not member_social_fund_account_id:
            from app.models.ledger import LedgerAccount, AccountType
            member_social_fund = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == deposit.member_id,
                LedgerAccount.account_name.ilike("%social fund%")
            ).first()
            
            if not member_social_fund:
                short_id = str(deposit.member_id).replace('-', '')[:8]
                member_social_fund = LedgerAccount(
                    account_code=f"MEM_SOC_{short_id}",
                    account_name=f"Social Fund - {deposit.member_id}",
                    account_type=AccountType.ASSET,
                    member_id=deposit.member_id,
                    description=f"Social fund receivable account for member {deposit.member_id}"
                )
                db.add(member_social_fund)
                db.flush()
                member_social_fund_account_id = member_social_fund.id
            else:
                member_social_fund_account_id = member_social_fund.id
        
        if member_social_fund_account_id:
            # Debit member account (payment - shown as debit per user requirement)
            lines.append({
                "account_id": member_social_fund_account_id,
                "debit_amount": social_fund,
                "credit_amount": Decimal("0.00"),
                "description": "Social fund payment"
            })
            
            # Credit organization receivable to balance
            from app.models.ledger import LedgerAccount, AccountType
            social_fund_receivable = db.query(LedgerAccount).filter(
                LedgerAccount.account_code == "SOC_FUND_REC"
            ).first()
            
            # Create receivable account if it doesn't exist
            if not social_fund_receivable:
                social_fund_receivable = LedgerAccount(
                    account_code="SOC_FUND_REC",
                    account_name="Social Fund Receivable",
                    account_type=AccountType.ASSET,
                    description="Social fund receivables from members (contra account for member social fund accounts)"
                )
                db.add(social_fund_receivable)
                db.flush()
            
            # Credit organization receivable to balance the payment debit
            lines.append({
                "account_id": social_fund_receivable.id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": social_fund,
                "description": "Social fund payment received (reduces receivable)"
            })
    
    # Credit member admin fund account (reduces outstanding balance)
    # Also debit organization receivable to balance
    if admin_fund > 0:
        # Get or create member's admin fund account if it doesn't exist
        if not member_admin_fund_account_id:
            from app.models.ledger import LedgerAccount, AccountType
            member_admin_fund = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == deposit.member_id,
                LedgerAccount.account_name.ilike("%admin fund%")
            ).first()
            
            if not member_admin_fund:
                short_id = str(deposit.member_id).replace('-', '')[:8]
                member_admin_fund = LedgerAccount(
                    account_code=f"MEM_ADM_{short_id}",
                    account_name=f"Admin Fund - {deposit.member_id}",
                    account_type=AccountType.ASSET,
                    member_id=deposit.member_id,
                    description=f"Admin fund receivable account for member {deposit.member_id}"
                )
                db.add(member_admin_fund)
                db.flush()
                member_admin_fund_account_id = member_admin_fund.id
            else:
                member_admin_fund_account_id = member_admin_fund.id
        
        if member_admin_fund_account_id:
            # Debit member account (payment - shown as debit per user requirement)
            lines.append({
                "account_id": member_admin_fund_account_id,
                "debit_amount": admin_fund,
                "credit_amount": Decimal("0.00"),
                "description": "Admin fund payment"
            })
            
            # Credit organization receivable to balance
            from app.models.ledger import LedgerAccount, AccountType
            admin_fund_receivable = db.query(LedgerAccount).filter(
                LedgerAccount.account_code == "ADM_FUND_REC"
            ).first()
            
            # Create receivable account if it doesn't exist
            if not admin_fund_receivable:
                admin_fund_receivable = LedgerAccount(
                    account_code="ADM_FUND_REC",
                    account_name="Admin Fund Receivable",
                    account_type=AccountType.ASSET,
                    description="Admin fund receivables from members (contra account for member admin fund accounts)"
                )
                db.add(admin_fund_receivable)
                db.flush()
            
            # Credit organization receivable to balance the payment debit
            lines.append({
                "account_id": admin_fund_receivable.id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": admin_fund,
                "description": "Admin fund payment received (reduces receivable)"
            })
    
    # Credit penalties payable
    if penalties > 0:
        # Get or create penalties payable account if it doesn't exist
        if not penalties_payable_account_id:
            from app.models.ledger import LedgerAccount, AccountType
            penalties_account = db.query(LedgerAccount).filter(
                LedgerAccount.member_id == deposit.member_id,
                LedgerAccount.account_name.ilike("%penalties payable%")
            ).first()
            
            if not penalties_account:
                short_id = str(deposit.member_id).replace('-', '')[:8]
                penalties_account = LedgerAccount(
                    account_code=f"PEN_PAY_{short_id}",
                    account_name=f"Penalties Payable - {deposit.member_id}",
                    account_type=AccountType.LIABILITY,
                    member_id=deposit.member_id,
                    description=f"Penalties payable account for member {deposit.member_id}"
                )
                db.add(penalties_account)
                db.flush()
                penalties_payable_account_id = penalties_account.id
            else:
                penalties_payable_account_id = penalties_account.id
        
        if penalties_payable_account_id:
            lines.append({
                "account_id": penalties_payable_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": penalties,
                "description": "Penalties payment"
            })
    
    # Credit interest income and reduce loan receivable (if accounts provided)
    if interest_on_loan > 0 and interest_income_account_id:
        lines.append({
            "account_id": interest_income_account_id,
            "debit_amount": Decimal("0.00"),
            "credit_amount": interest_on_loan,
            "description": "Interest on loan payment"
        })
    
    if loan_repayment > 0 and loans_receivable_account_id:
        # Credit loan receivable (reduces the receivable balance)
        lines.append({
            "account_id": loans_receivable_account_id,
            "debit_amount": Decimal("0.00"),
            "credit_amount": loan_repayment,
            "description": "Loan principal repayment"
        })
    
    # Create journal entry
    journal_entry = create_journal_entry(
        db=db,
        description=f"Deposit approval for member {deposit.member_id} - Declaration {declaration.effective_month}",
        lines=lines,
        cycle_id=deposit.cycle_id,
        source_ref=str(deposit.id),
        source_type="deposit_approval",
        created_by=approved_by
    )
    
    # Create approval record
    approval = DepositApproval(
        deposit_proof_id=deposit.id,
        journal_entry_id=journal_entry.id,
        approved_by=approved_by
    )
    db.add(approval)
    
    # Update deposit proof status to APPROVED
    deposit.status = DepositProofStatus.APPROVED.value
    
    # Update declaration status to APPROVED
    declaration.status = DeclarationStatus.APPROVED
    
    db.commit()
    db.refresh(approval)
    return approval


def disburse_loan(
    db: Session,
    loan_id: UUID,
    disbursed_by: UUID,
    bank_cash_account_id: UUID,
    loans_receivable_account_id: UUID
) -> Loan:
    """Disburse a loan and post to ledger.
    
    Creates journal entry:
    - Debit: Loans Receivable (asset)
    - Credit: Bank Cash (asset)
    
    The loan is posted to the member's account (visible in loan balance).
    """
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("Loan not found")
    
    if loan.loan_status not in [LoanStatus.APPROVED]:
        raise ValueError("Loan must be approved before disbursement")
    
    # Create journal entry
    journal_entry = create_journal_entry(
        db=db,
        description=f"Loan disbursement for loan {loan.id}",
        lines=[
            {
                "account_id": loans_receivable_account_id,
                "debit_amount": loan.loan_amount,
                "credit_amount": Decimal("0.00"),
                "description": f"Loan receivable - {loan.member_id}"
            },
            {
                "account_id": bank_cash_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": loan.loan_amount,
                "description": "Bank cash disbursed"
            }
        ],
        cycle_id=loan.cycle_id,
        source_ref=str(loan.id),
        source_type="loan_disbursement",
        created_by=disbursed_by
    )
    
    loan.loan_status = LoanStatus.OPEN  # Set to OPEN (active) after disbursement
    loan.disbursement_date = date.today()
    loan.disbursement_journal_entry_id = journal_entry.id
    
    db.commit()
    db.refresh(loan)
    return loan


def post_repayment(
    db: Session,
    loan_id: UUID,
    repayment_date: date,
    principal_amount: Decimal,
    interest_amount: Decimal,
    bank_cash_account_id: UUID,
    loans_receivable_account_id: UUID,
    interest_income_account_id: UUID,
    created_by: UUID = None
) -> Repayment:
    """Post a loan repayment to ledger."""
    total_amount = principal_amount + interest_amount
    
    # Create journal entry
    journal_entry = create_journal_entry(
        db=db,
        description=f"Loan repayment for loan {loan_id}",
        lines=[
            {
                "account_id": bank_cash_account_id,
                "debit_amount": total_amount,
                "credit_amount": Decimal("0.00"),
                "description": "Bank cash received"
            },
            {
                "account_id": loans_receivable_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": principal_amount,
                "description": "Principal repayment"
            },
            {
                "account_id": interest_income_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": interest_amount,
                "description": "Interest income"
            }
        ],
        source_ref=str(loan_id),
        source_type="repayment",
        created_by=created_by
    )
    
    # Create repayment record
    repayment = Repayment(
        loan_id=loan_id,
        repayment_date=repayment_date,
        principal_amount=principal_amount,
        interest_amount=interest_amount,
        total_amount=total_amount,
        journal_entry_id=journal_entry.id
    )
    db.add(repayment)
    db.commit()
    db.refresh(repayment)
    return repayment


def approve_penalty(
    db: Session,
    penalty_record_id: UUID,
    approved_by: UUID,
    member_savings_account_id: UUID,
    penalty_income_account_id: UUID
) -> PenaltyRecord:
    """Approve penalty and post to ledger."""
    penalty = db.query(PenaltyRecord).filter(PenaltyRecord.id == penalty_record_id).first()
    if not penalty:
        raise ValueError("Penalty record not found")
    
    # Check if penalty is already posted
    if penalty.status == PenaltyRecordStatus.POSTED:
        raise ValueError("Penalty has already been posted")
    
    # Check if penalty has a penalty_type_id
    if not penalty.penalty_type_id:
        raise ValueError("Penalty record is missing penalty type")
    
    penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty.penalty_type_id).first()
    if not penalty_type:
        raise ValueError(f"Penalty type with ID {penalty.penalty_type_id} not found")
    
    # Check if penalty type has a valid fee amount
    if penalty_type.fee_amount is None or penalty_type.fee_amount <= Decimal("0.00"):
        raise ValueError(f"Penalty type '{penalty_type.name}' has invalid fee amount")
    
    # Create journal entry
    journal_entry = create_journal_entry(
        db=db,
        description=f"Penalty for member {penalty.member_id}",
        lines=[
            {
                "account_id": member_savings_account_id,
                "debit_amount": penalty_type.fee_amount,
                "credit_amount": Decimal("0.00"),
                "description": "Penalty charged to member"
            },
            {
                "account_id": penalty_income_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": penalty_type.fee_amount,
                "description": "Penalty income"
            }
        ],
        source_ref=str(penalty.id),
        source_type="penalty",
        created_by=approved_by
    )
    
    penalty.status = PenaltyRecordStatus.POSTED
    penalty.approved_by = approved_by
    penalty.approved_at = datetime.utcnow()
    penalty.journal_entry_id = journal_entry.id
    
    db.commit()
    db.refresh(penalty)
    return penalty
