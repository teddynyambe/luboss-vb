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
        # Debug: Print all lines for troubleshooting
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Journal entry imbalance detected:")
        logger.error(f"  Description: {description}")
        logger.error(f"  Total Debits: {total_debits}, Total Credits: {total_credits}")
        for i, line in enumerate(lines):
            logger.error(f"  Line {i+1}: Account={line.get('account_id')}, Debit={line.get('debit_amount', 0)}, Credit={line.get('credit_amount', 0)}, Desc={line.get('description', 'N/A')}")
        raise JournalEntryError(
            f"Journal entry is not balanced: debits={total_debits}, credits={total_credits}. Difference: {total_debits - total_credits}"
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
    """Get member's savings balance from ledger.
    
    Returns only credits from deposit approvals (actual deposits received),
    excluding penalty debits. This shows the accumulation of actual proof of
    payment received for declarations, not reduced by penalties.
    """
    from sqlalchemy import func
    from app.models.transaction import DepositProof, DepositApproval
    
    # Find member's savings account
    savings_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    
    if not savings_account:
        return Decimal("0.00")
    
    # Query 1: credits from deposit approvals (existing logic)
    q1 = db.query(func.sum(JournalLine.credit_amount)).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).join(
        DepositApproval, JournalEntry.id == DepositApproval.journal_entry_id
    ).join(
        DepositProof, DepositApproval.deposit_proof_id == DepositProof.id
    ).filter(
        JournalLine.ledger_account_id == savings_account.id,
        DepositProof.member_id == member_id,
        JournalEntry.reversed_by.is_(None),
        JournalEntry.source_type == "deposit_approval",
    )
    if as_of_date:
        q1 = q1.filter(JournalEntry.entry_date <= as_of_date)
    deposit_credits = q1.scalar() or Decimal("0.00")

    # Query 2: credits from excess contribution transfers
    q2 = db.query(func.sum(JournalLine.credit_amount)).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).filter(
        JournalLine.ledger_account_id == savings_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalEntry.source_type == "excess_contribution",
        JournalLine.credit_amount > 0,
    )
    if as_of_date:
        q2 = q2.filter(JournalEntry.entry_date <= as_of_date)
    excess_credits = q2.scalar() or Decimal("0.00")

    return deposit_credits + excess_credits


def get_member_loan_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's outstanding loan balance.

    Calculates by summing active loan amounts and subtracting principal paid.
    Principal paid is sourced from APPROVED declarations (declared_loan_repayment),
    which covers both historical deposits (no Repayment record) and new ones equally.
    """
    from app.models.transaction import Loan, LoanStatus, Declaration, DeclarationStatus

    # Get all active loans (OPEN or DISBURSED) for this member
    loan_query = db.query(Loan).filter(
        Loan.member_id == member_id,
        Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED])
    )
    if as_of_date:
        loan_query = loan_query.filter(Loan.created_at <= as_of_date)

    active_loans = loan_query.all()
    if not active_loans:
        return Decimal("0.00")

    total_outstanding = Decimal("0.00")

    for loan in active_loans:
        # Sum principal paid from approved declarations dated on/after disbursement
        decl_query = db.query(Declaration).filter(
            Declaration.member_id == member_id,
            Declaration.status == DeclarationStatus.APPROVED,
            Declaration.declared_loan_repayment > 0,
        )
        if loan.disbursement_date:
            decl_query = decl_query.filter(
                Declaration.effective_month >= loan.disbursement_date
            )
        if as_of_date:
            decl_query = decl_query.filter(
                Declaration.effective_month <= as_of_date.date()
            )

        total_principal_paid = sum(
            (decl.declared_loan_repayment or Decimal("0.00"))
            for decl in decl_query.all()
        )

        outstanding = loan.loan_amount - total_principal_paid
        total_outstanding += outstanding

    return max(Decimal("0.00"), total_outstanding)


def get_member_social_fund_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's social fund balance due from ledger.
    
    Returns balance due = Total Debits (required amounts) - Total Credits (payments).
    This is a balance-due account where:
    - Required amount → Debit (increases balance)
    - Payment → Credit (reduces balance)
    - Balance = Debits - Credits
    """
    from app.models.ledger import JournalLine, JournalEntry
    
    # Find member's social fund account (member-specific)
    member_social_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%social fund%")
    ).first()
    
    if not member_social_fund_account:
        return Decimal("0.00")
    
    # Get total debits (required amounts) and total credits (payments)
    query_debits = db.query(func.sum(JournalLine.debit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_social_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalLine.debit_amount > 0
    )
    query_credits = db.query(func.sum(JournalLine.credit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_social_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalLine.credit_amount > 0
    )
    
    if as_of_date:
        query_debits = query_debits.filter(JournalEntry.entry_date <= as_of_date)
        query_credits = query_credits.filter(JournalEntry.entry_date <= as_of_date)
    
    total_debits = query_debits.scalar() or Decimal("0.00")
    total_credits = query_credits.scalar() or Decimal("0.00")
    
    # Balance = Debits - Credits (balance due)
    balance_due = total_debits - total_credits
    
    return max(Decimal("0.00"), balance_due)  # Ensure non-negative


def get_member_social_fund_payments(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's social fund accumulated payments from ledger.
    
    Returns total accumulated payments made (sum of all credits/payments).
    This shows how much the member has paid towards their social fund requirement.
    """
    from app.models.ledger import JournalLine, JournalEntry
    
    # Find member's social fund account (member-specific)
    member_social_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%social fund%")
    ).first()
    
    if not member_social_fund_account:
        return Decimal("0.00")
    
    # Get total credits (payments) - also handle legacy debits as payments
    query_credits = db.query(func.sum(JournalLine.credit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_social_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalEntry.source_type == "deposit_approval",  # Only payment entries
        JournalLine.credit_amount > 0
    )
    query_debits = db.query(func.sum(JournalLine.debit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_social_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalEntry.source_type == "deposit_approval",  # Only payment entries
        JournalLine.debit_amount > 0
    )
    
    if as_of_date:
        query_credits = query_credits.filter(JournalEntry.entry_date <= as_of_date)
        query_debits = query_debits.filter(JournalEntry.entry_date <= as_of_date)
    
    total_credits = query_credits.scalar() or Decimal("0.00")
    total_debits = query_debits.scalar() or Decimal("0.00")
    
    # Accumulated payments = credits (new) + debits (legacy)
    accumulated_payments = total_credits + total_debits
    
    return max(Decimal("0.00"), accumulated_payments)  # Ensure non-negative


def get_member_admin_fund_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's admin fund balance due from ledger.
    
    Returns balance due = Total Debits (required amounts) - Total Credits (payments).
    This is a balance-due account where:
    - Required amount → Debit (increases balance)
    - Payment → Credit (reduces balance)
    - Balance = Debits - Credits
    """
    from app.models.ledger import JournalLine, JournalEntry
    
    # Find member's admin fund account (member-specific)
    member_admin_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%admin fund%")
    ).first()
    
    if not member_admin_fund_account:
        return Decimal("0.00")
    
    # Get total debits (required amounts) and total credits (payments)
    query_debits = db.query(func.sum(JournalLine.debit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_admin_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalLine.debit_amount > 0
    )
    query_credits = db.query(func.sum(JournalLine.credit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_admin_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalLine.credit_amount > 0
    )
    
    if as_of_date:
        query_debits = query_debits.filter(JournalEntry.entry_date <= as_of_date)
        query_credits = query_credits.filter(JournalEntry.entry_date <= as_of_date)
    
    total_debits = query_debits.scalar() or Decimal("0.00")
    total_credits = query_credits.scalar() or Decimal("0.00")
    
    # Balance = Debits - Credits (balance due)
    balance_due = total_debits - total_credits
    
    return max(Decimal("0.00"), balance_due)  # Ensure non-negative


def get_member_admin_fund_payments(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's admin fund accumulated payments from ledger.
    
    Returns total accumulated payments made (sum of all credits/payments).
    This shows how much the member has paid towards their admin fund requirement.
    """
    from app.models.ledger import JournalLine, JournalEntry
    
    # Find member's admin fund account (member-specific)
    member_admin_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%admin fund%")
    ).first()
    
    if not member_admin_fund_account:
        return Decimal("0.00")
    
    # Get total credits (payments) - also handle legacy debits as payments
    query_credits = db.query(func.sum(JournalLine.credit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_admin_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalEntry.source_type == "deposit_approval",  # Only payment entries
        JournalLine.credit_amount > 0
    )
    query_debits = db.query(func.sum(JournalLine.debit_amount)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_admin_fund_account.id,
        JournalEntry.reversed_by.is_(None),
        JournalEntry.source_type == "deposit_approval",  # Only payment entries
        JournalLine.debit_amount > 0
    )
    
    if as_of_date:
        query_credits = query_credits.filter(JournalEntry.entry_date <= as_of_date)
        query_debits = query_debits.filter(JournalEntry.entry_date <= as_of_date)
    
    total_credits = query_credits.scalar() or Decimal("0.00")
    total_debits = query_debits.scalar() or Decimal("0.00")
    
    # Accumulated payments = credits (new) + debits (legacy)
    accumulated_payments = total_credits + total_debits
    
    return max(Decimal("0.00"), accumulated_payments)  # Ensure non-negative


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
