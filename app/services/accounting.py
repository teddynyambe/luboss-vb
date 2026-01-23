from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.ledger import LedgerAccount, JournalEntry, JournalLine, AccountType
from app.models.member import MemberProfile
from decimal import Decimal
from typing import List, Dict
from uuid import UUID
from datetime import datetime


class JournalEntryError(Exception):
    """Exception for journal entry errors."""
    pass


def create_journal_entry(
    db: Session,
    description: str,
    lines: List[Dict],
    cycle_id: UUID = None,
    source_ref: str = None,
    source_type: str = None,
    created_by: UUID = None
) -> JournalEntry:
    """
    Create a balanced journal entry.
    
    Args:
        lines: List of dicts with keys: account_id, debit_amount, credit_amount, description
    """
    # Validate balance
    total_debits = sum(Decimal(str(line.get("debit_amount", 0))) for line in lines)
    total_credits = sum(Decimal(str(line.get("credit_amount", 0))) for line in lines)
    
    if total_debits != total_credits:
        raise JournalEntryError(
            f"Journal entry is not balanced: debits={total_debits}, credits={total_credits}"
        )
    
    # Create journal entry
    journal_entry = JournalEntry(
        description=description,
        cycle_id=cycle_id,
        source_ref=source_ref,
        source_type=source_type,
        created_by=created_by
    )
    db.add(journal_entry)
    db.flush()
    
    # Create journal lines
    for line in lines:
        journal_line = JournalLine(
            journal_entry_id=journal_entry.id,
            ledger_account_id=line["account_id"],
            debit_amount=Decimal(str(line.get("debit_amount", 0))),
            credit_amount=Decimal(str(line.get("credit_amount", 0))),
            description=line.get("description")
        )
        db.add(journal_line)
    
    db.commit()
    db.refresh(journal_entry)
    return journal_entry


def get_account_balance(
    db: Session,
    account_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get account balance (debits - credits for assets, credits - debits for liabilities/income/equity)."""
    query = db.query(
        func.sum(JournalLine.debit_amount).label("total_debits"),
        func.sum(JournalLine.credit_amount).label("total_credits")
    ).join(JournalEntry).filter(
        JournalLine.ledger_account_id == account_id
    )
    
    if as_of_date:
        query = query.filter(JournalEntry.entry_date <= as_of_date)
    
    result = query.first()
    total_debits = result.total_debits or Decimal("0.00")
    total_credits = result.total_credits or Decimal("0.00")
    
    # Get account type to determine balance calculation
    account = db.query(LedgerAccount).filter(LedgerAccount.id == account_id).first()
    if not account:
        return Decimal("0.00")
    
    if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
        return total_debits - total_credits
    else:  # LIABILITY, INCOME, EQUITY
        return total_credits - total_debits


def get_member_savings_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's savings balance from ledger."""
    # Find member's savings account
    account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    
    if not account:
        return Decimal("0.00")
    
    return get_account_balance(db, account.id, as_of_date)


def get_member_loan_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's outstanding loan balance.
    
    Calculates by summing all active loan amounts and subtracting principal repayments.
    """
    from app.models.transaction import Loan, LoanStatus, Repayment
    
    # Get all active loans (OPEN status) for this member
    query = db.query(Loan).filter(
        Loan.member_id == member_id,
        Loan.loan_status == LoanStatus.OPEN
    )
    
    if as_of_date:
        # Filter loans created before or on the date
        query = query.filter(Loan.created_at <= as_of_date)
    
    active_loans = query.all()
    
    if not active_loans:
        return Decimal("0.00")
    
    # Calculate total outstanding balance
    total_outstanding = Decimal("0.00")
    
    for loan in active_loans:
        # Get total principal paid for this loan
        repayments_query = db.query(Repayment).filter(Repayment.loan_id == loan.id)
        if as_of_date:
            repayments_query = repayments_query.filter(Repayment.repayment_date <= as_of_date.date())
        
        total_principal_paid = sum(
            repayment.principal_amount 
            for repayment in repayments_query.all()
        )
        
        # Outstanding balance = loan amount - principal paid
        outstanding = loan.loan_amount - total_principal_paid
        total_outstanding += outstanding
    
    return max(Decimal("0.00"), total_outstanding)  # Ensure non-negative


def get_member_social_fund_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's total social fund contributions from ledger."""
    from sqlalchemy import and_, func
    
    # Find organization's social fund account (not member-specific)
    social_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "SOCIAL_FUND"
    ).first()
    
    if not social_fund_account:
        return Decimal("0.00")
    
    # Sum all credits to social fund account from this member's deposits
    # We find journal entries linked to this member through deposit proofs
    from app.models.transaction import DepositProof, DepositApproval
    
    query = db.query(func.sum(JournalLine.credit_amount)).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).join(
        DepositApproval, JournalEntry.id == DepositApproval.journal_entry_id
    ).join(
        DepositProof, DepositApproval.deposit_proof_id == DepositProof.id
    ).filter(
        JournalLine.ledger_account_id == social_fund_account.id,
        DepositProof.member_id == member_id,
        JournalEntry.reversed_by.is_(None)  # Exclude reversed entries
    )
    
    if as_of_date:
        query = query.filter(JournalEntry.entry_date <= as_of_date)
    
    result = query.scalar()
    return Decimal(str(result)) if result else Decimal("0.00")


def get_member_admin_fund_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's total admin fund contributions from ledger."""
    from sqlalchemy import and_, func
    
    # Find organization's admin fund account (not member-specific)
    admin_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "ADMIN_FUND"
    ).first()
    
    if not admin_fund_account:
        return Decimal("0.00")
    
    # Sum all credits to admin fund account from this member's deposits
    # We find journal entries linked to this member through deposit proofs
    from app.models.transaction import DepositProof, DepositApproval
    
    query = db.query(func.sum(JournalLine.credit_amount)).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).join(
        DepositApproval, JournalEntry.id == DepositApproval.journal_entry_id
    ).join(
        DepositProof, DepositApproval.deposit_proof_id == DepositProof.id
    ).filter(
        JournalLine.ledger_account_id == admin_fund_account.id,
        DepositProof.member_id == member_id,
        JournalEntry.reversed_by.is_(None)  # Exclude reversed entries
    )
    
    if as_of_date:
        query = query.filter(JournalEntry.entry_date <= as_of_date)
    
    result = query.scalar()
    return Decimal(str(result)) if result else Decimal("0.00")


def get_member_penalties_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's penalties balance from ledger."""
    # Find member's penalties account
    account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%penalties%")
    ).first()
    
    if not account:
        return Decimal("0.00")
    
    return get_account_balance(db, account.id, as_of_date)
