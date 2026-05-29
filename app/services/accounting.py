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
    """Get member's savings balance from the ledger.

    Standard liability-account balance: total live credits − total live debits.
    Any source_type is included (deposit_approval, excess_contribution,
    transaction_split, …) so that treasurer corrections via the Posted
    Transactions tools flow through automatically.
    """
    from sqlalchemy import func

    savings_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    if not savings_account:
        return Decimal("0.00")

    q_credits = db.query(func.coalesce(func.sum(JournalLine.credit_amount), 0)).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).filter(
        JournalLine.ledger_account_id == savings_account.id,
        JournalEntry.reversed_by.is_(None),
    )
    q_debits = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0)).join(
        JournalEntry, JournalLine.journal_entry_id == JournalEntry.id
    ).filter(
        JournalLine.ledger_account_id == savings_account.id,
        JournalEntry.reversed_by.is_(None),
    )
    if as_of_date:
        q_credits = q_credits.filter(JournalEntry.entry_date <= as_of_date)
        q_debits = q_debits.filter(JournalEntry.entry_date <= as_of_date)

    credits = Decimal(str(q_credits.scalar() or 0))
    debits = Decimal(str(q_debits.scalar() or 0))
    return max(Decimal("0.00"), credits - debits)


def get_member_loan_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's outstanding loan balance.

    Principal paid is sourced from Repayment rows whose linked JournalEntry has
    not been reversed. This matches the ledger statement (LOANS_RECEIVABLE
    credits on live entries), so reconciliation reversals are honored.
    """
    from app.models.transaction import Loan, LoanStatus, Repayment
    from app.models.ledger import JournalEntry
    from sqlalchemy import or_ as _or_

    if as_of_date:
        # "What was outstanding at this point in time": include OPEN/DISBURSED
        # loans whose disbursement happened on or before the cutoff. Closed
        # loans are excluded — by definition they were fully paid off, so they
        # contribute 0 to outstanding anyway, and excluding them avoids
        # double-counting closed-with-stale-data records.
        cutoff_date = as_of_date.date() if hasattr(as_of_date, "date") else as_of_date
        loan_query = db.query(Loan).filter(
            Loan.member_id == member_id,
            Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED]),
            Loan.disbursement_date.isnot(None),
            Loan.disbursement_date <= cutoff_date,
        )
    else:
        loan_query = db.query(Loan).filter(
            Loan.member_id == member_id,
            Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED])
        )

    active_loans = loan_query.all()
    if not active_loans:
        return Decimal("0.00")

    total_outstanding = Decimal("0.00")
    for loan in active_loans:
        rep_q = (
            db.query(func.coalesce(func.sum(Repayment.principal_amount), 0))
            .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
            .filter(
                Repayment.loan_id == loan.id,
                JournalEntry.reversed_by.is_(None),
                JournalEntry.reversed_at.is_(None),
            )
        )
        if as_of_date:
            cutoff = as_of_date.date() if hasattr(as_of_date, "date") else as_of_date
            rep_q = rep_q.filter(Repayment.repayment_date <= cutoff)
        total_principal_paid = Decimal(str(rep_q.scalar() or 0))
        total_outstanding += (loan.loan_amount - total_principal_paid)

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
    """Get member's net social fund balance (payments minus excess transfers).

    Returns the amount currently held in the member's social fund after any
    excess contributions have been reclassified to savings by the scheduler.
    """
    from app.models.ledger import JournalLine, JournalEntry

    member_social_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%social fund%")
    ).first()
    if not member_social_fund_account:
        return Decimal("0.00")

    # Standard liability-account balance: live credits − live debits, any source.
    # Splits, reverses and excess transfers all reflect automatically.
    q_credits = db.query(func.coalesce(func.sum(JournalLine.credit_amount), 0)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_social_fund_account.id,
        JournalEntry.reversed_by.is_(None),
    )
    q_debits = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_social_fund_account.id,
        JournalEntry.reversed_by.is_(None),
    )
    if as_of_date:
        q_credits = q_credits.filter(JournalEntry.entry_date <= as_of_date)
        q_debits = q_debits.filter(JournalEntry.entry_date <= as_of_date)
    credits = Decimal(str(q_credits.scalar() or 0))
    debits = Decimal(str(q_debits.scalar() or 0))
    return max(Decimal("0.00"), credits - debits)


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
    """Get member's net admin fund balance (payments minus excess transfers).

    Returns the amount currently held in the member's admin fund after any
    excess contributions have been reclassified to savings by the scheduler.
    """
    from app.models.ledger import JournalLine, JournalEntry

    member_admin_fund_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%admin fund%")
    ).first()
    if not member_admin_fund_account:
        return Decimal("0.00")

    # Same as social fund payments: live credits − live debits, any source_type.
    q_credits = db.query(func.coalesce(func.sum(JournalLine.credit_amount), 0)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_admin_fund_account.id,
        JournalEntry.reversed_by.is_(None),
    )
    q_debits = db.query(func.coalesce(func.sum(JournalLine.debit_amount), 0)).join(JournalEntry).filter(
        JournalLine.ledger_account_id == member_admin_fund_account.id,
        JournalEntry.reversed_by.is_(None),
    )
    if as_of_date:
        q_credits = q_credits.filter(JournalEntry.entry_date <= as_of_date)
        q_debits = q_debits.filter(JournalEntry.entry_date <= as_of_date)
    credits = Decimal(str(q_credits.scalar() or 0))
    debits = Decimal(str(q_debits.scalar() or 0))
    return max(Decimal("0.00"), credits - debits)


def compute_posted_breakdown(
    db: Session,
    member_id: UUID,
    year: int,
    month: int,
) -> dict:
    """Return per-category live posted amounts for this member in a given month.

    Each live journal line on the member's category accounts is bucketed by:
      1. The declaration's effective_month, if the line traces to one (via
         DepositApproval → DepositProof → Declaration). This handles the
         common case of a March declaration whose deposit is approved in
         April — the line still belongs to March.
      2. For a 'transaction_split' JE, the same trace follows the split's
         source line back to its declaration.
      3. Otherwise, JournalEntry.entry_date is used as the fallback (excess
         transfers and other anchor-less adjustments).

    Returns the sum of (credit − debit) for each of savings / social_fund /
    admin_fund / penalty that bucketed into the target (year, month).
    Reversed JEs are excluded.
    """
    from app.models.ledger import JournalLine, JournalEntry
    from app.models.transaction import DepositApproval, DepositProof, Declaration
    import uuid as _uuid

    category_filters = {
        "savings": "%savings%",
        "social_fund": "%social fund%",
        "admin_fund": "%admin fund%",
        "penalty": "%penalt%",
    }
    posted: dict[str, float] = {k: 0.0 for k in category_filters}

    # Build a JE → (year, month) bucket cache so we don't re-walk the chain
    # for every line of the same JE.
    je_bucket_cache: dict[UUID, tuple[int, int] | None] = {}

    def _bucket_for_je(je: JournalEntry) -> tuple[int, int] | None:
        if je.id in je_bucket_cache:
            return je_bucket_cache[je.id]
        ym: tuple[int, int] | None = None

        # 1. JE is a deposit approval (or any JE with a matching DepositApproval).
        approval = db.query(DepositApproval).filter(
            DepositApproval.journal_entry_id == je.id
        ).first()
        if approval:
            proof = db.query(DepositProof).filter(
                DepositProof.id == approval.deposit_proof_id
            ).first()
            if proof and proof.declaration_id:
                decl = db.query(Declaration).filter(
                    Declaration.id == proof.declaration_id
                ).first()
                if decl and decl.effective_month:
                    ym = (decl.effective_month.year, decl.effective_month.month)

        # 2. JE is a split — follow source_ref back to original line's JE.
        if ym is None and je.source_type == "transaction_split" and je.source_ref:
            try:
                src_line_id = _uuid.UUID(je.source_ref)
                src_line = db.query(JournalLine).filter(JournalLine.id == src_line_id).first()
                if src_line:
                    src_je = db.query(JournalEntry).filter(
                        JournalEntry.id == src_line.journal_entry_id
                    ).first()
                    if src_je:
                        ym = _bucket_for_je(src_je)
            except (ValueError, TypeError):
                pass

        # 3. Fallback to the JE's own entry_date.
        if ym is None and je.entry_date:
            ym = (je.entry_date.year, je.entry_date.month)

        je_bucket_cache[je.id] = ym
        return ym

    for category, name_filter in category_filters.items():
        account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member_id,
            LedgerAccount.account_name.ilike(name_filter),
        ).first()
        if not account:
            continue
        rows = (
            db.query(JournalLine, JournalEntry)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .filter(
                JournalLine.ledger_account_id == account.id,
                JournalEntry.reversed_by.is_(None),
            )
            .all()
        )
        for line, je in rows:
            ym = _bucket_for_je(je)
            if ym is None or ym != (year, month):
                continue
            cred = Decimal(str(line.credit_amount or 0))
            deb = Decimal(str(line.debit_amount or 0))
            posted[category] += float(cred - deb)

    return posted


def get_member_penalties_balance(
    db: Session,
    member_id: UUID,
    as_of_date: datetime = None
) -> Decimal:
    """Get member's penalties balance from the ledger, excluding reversed entries.

    Uses the Penalties Payable account (LIABILITY).  For a liability account
    the balance is credits minus debits.  Only non-reversed journal entries
    are included so that voided transactions don't inflate the total.
    """
    from app.models.ledger import JournalLine, JournalEntry

    account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%penalties%")
    ).first()

    if not account:
        return Decimal("0.00")

    query = db.query(
        func.sum(JournalLine.credit_amount).label("total_credits"),
        func.sum(JournalLine.debit_amount).label("total_debits"),
    ).join(JournalEntry).filter(
        JournalLine.ledger_account_id == account.id,
        JournalEntry.reversed_by.is_(None),
    )

    if as_of_date:
        query = query.filter(JournalEntry.entry_date <= as_of_date)

    result = query.first()
    total_credits = result.total_credits or Decimal("0.00")
    total_debits = result.total_debits or Decimal("0.00")

    # LIABILITY: balance = credits - debits
    return max(Decimal("0.00"), total_credits - total_debits)
