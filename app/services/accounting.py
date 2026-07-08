from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.ledger import LedgerAccount, JournalEntry, JournalLine, AccountType
from app.models.member import MemberProfile
from decimal import Decimal
from typing import List, Dict
from uuid import UUID
from datetime import datetime, date


def get_dealing_month_date(db: Session, cycle_id: UUID | None, effective_month: date) -> date:
    """Return the start-of-dealing-month date for a journal entry.

    The "dealing month" anchors a transaction to a reporting period regardless of
    when it was actually posted. The day-of-month comes from the cycle's
    DECLARATION phase `monthly_start_day` (e.g. 15 → May 15 for a May dealing month).
    Falls back to day 1 if no cycle is supplied or no phase day is configured.
    """
    from app.models.cycle import CyclePhase, PhaseType

    day = 1
    if cycle_id is not None:
        phase = (
            db.query(CyclePhase)
            .filter(
                CyclePhase.cycle_id == cycle_id,
                CyclePhase.phase_type == PhaseType.DECLARATION,
            )
            .first()
        )
        if phase and phase.monthly_start_day:
            day = int(phase.monthly_start_day)

    # Clamp to a safe day in case the cycle's start_day exceeds the month length.
    import calendar
    last_day = calendar.monthrange(effective_month.year, effective_month.month)[1]
    day = min(day, last_day)
    return date(effective_month.year, effective_month.month, day)


class JournalEntryError(Exception):
    """Exception for journal entry errors."""
    pass


def create_journal_entry(
    db: Session,
    description: str,
    lines: List[Dict],
    dealing_month: date,
    cycle_id: UUID = None,
    source_ref: str = None,
    source_type: str = None,
    created_by: UUID = None
) -> JournalEntry:
    """
    Create a balanced journal entry.

    Args:
        dealing_month: The reporting period this entry is allocated to
            (start-of-dealing-month date — see ``get_dealing_month_date``).
            This is independent of ``entry_date`` (the actual posting timestamp).
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
        dealing_month=dealing_month,
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

    Bucketing is now driven by ``JournalEntry.dealing_month`` — the explicit
    reporting period each entry is allocated to. Reversed JEs are excluded.
    """
    from app.models.ledger import JournalLine, JournalEntry

    category_filters = {
        "savings": "%savings%",
        "social_fund": "%social fund%",
        "admin_fund": "%admin fund%",
        "penalty": "%penalt%",
    }
    posted: dict[str, float] = {k: 0.0 for k in category_filters}

    def _bucket_for_je(je: JournalEntry) -> tuple[int, int] | None:
        if je.dealing_month is None:
            return None
        return (je.dealing_month.year, je.dealing_month.month)

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


def get_reconciliation_notes(
    db: Session,
    member_id: UUID,
    year: int,
    month: int,
) -> list[dict]:
    """Return human-readable notes from treasurer repair actions that affected
    this member's category accounts within the given dealing month.

    Used to surface the *actual* reason a posted amount differs from declared
    (e.g. "Reverse Savings: paid duplicate of K500" rather than the generic
    "treasurer reconciled" tooltip).

    Looks at JournalEntries with repair-action source_types whose dealing_month
    matches AND that have at least one line on a ledger account belonging to
    this member.

    Returns a list of {action, description, dealing_month} sorted by entry_date.
    Excludes reversed JEs (their effect was undone).
    """
    from app.models.ledger import JournalEntry, JournalLine, LedgerAccount

    REPAIR_TYPES = {
        "transaction_reverse": "Reversed",
        "transaction_split": "Split",
        "reversal": "Reversed",
        "penalty_reversal": "Penalty reversed",
        "loan_consolidation": "Loan consolidated",
        "repayment_split_adjustment": "Repayment split adjusted",
        "interest_accrual_retrofit": "Interest accrual retrofit",
        # Per-category correcting JE posted when a treasurer edits an
        # already-approved declaration from the Reports → Declaration Details
        # modal. Shows up under the affected member/month in reconciliation notes.
        "declaration_edit": "Declaration edited",
    }

    member_account_ids = (
        db.query(LedgerAccount.id)
        .filter(LedgerAccount.member_id == member_id)
        .subquery()
    )

    rows = (
        db.query(JournalEntry)
        .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
        .filter(
            JournalEntry.source_type.in_(list(REPAIR_TYPES.keys())),
            JournalEntry.reversed_by.is_(None),
            JournalEntry.reversed_at.is_(None),
            JournalEntry.dealing_month.isnot(None),
            func.extract("year", JournalEntry.dealing_month) == year,
            func.extract("month", JournalEntry.dealing_month) == month,
            JournalLine.ledger_account_id.in_(member_account_ids),
        )
        .distinct()
        .order_by(JournalEntry.entry_date.asc())
        .all()
    )

    return [
        {
            "action": REPAIR_TYPES.get(je.source_type or "", je.source_type or "Repair"),
            "description": je.description or "",
            "dealing_month": je.dealing_month.isoformat() if je.dealing_month else None,
        }
        for je in rows
    ]


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


def get_member_monthly_loan_balances(db: Session, member_id: UUID) -> list[dict]:
    """Per-month cumulative loan + interest receivable balances for a member.

    For each month from the member's earliest loan disbursement through today,
    returns the end-of-month outstanding principal and outstanding interest
    receivable. Outstanding interest follows the **accrual-at-origination**
    convention: when a loan is disbursed, its full expected interest
    (loan_amount × rate / 100) becomes receivable; interest payments draw
    that down.

    Months with no activity still appear, so the frontend can render a
    continuous timeline.

    Returns: list of dicts ordered oldest-first:
        {
            "month": "YYYY-MM-DD",   # first day of the month
            "loan_balance": float,
            "interest_balance": float,
            "loans_disbursed_this_month": [
                {"loan_id": str, "amount": float, "expected_interest": float},
                ...
            ],
            "repayments_this_month": [
                {
                    "loan_id": str,
                    "loan_label": str,         # e.g. "April 2026 (c11452f2)"
                    "date": "YYYY-MM-DD",
                    "principal": float,
                    "interest": float,
                    "total": float,
                    "was_carved_out": bool,    # True if this is a portion moved
                                               # in from another loan via the
                                               # treasurer's carve-out tool
                    "narration": str | None,   # human-readable JE description
                                               # when was_carved_out is True
                },
                ...
            ],
        }
    """
    from app.models.transaction import Loan, Repayment
    from app.models.ledger import JournalEntry
    from datetime import date as _date

    # Skip loans whose disbursement has been reversed — the loan record stays
    # in the table after reversal (for audit), but its ledger effect is undone
    # so it shouldn't carry into running balances.
    from app.services.loan_repair import loan_has_live_disbursement
    all_loans = (
        db.query(Loan)
        .filter(Loan.member_id == member_id, Loan.disbursement_date.isnot(None))
        .order_by(Loan.disbursement_date.asc())
        .all()
    )
    loans = [L for L in all_loans if loan_has_live_disbursement(db, L.id)]
    if not loans:
        return []

    earliest = min(L.disbursement_date for L in loans)
    today = _date.today()

    # Walk months from earliest disbursement → current month, inclusive.
    months: list[_date] = []
    y, m = earliest.year, earliest.month
    while (y, m) <= (today.year, today.month):
        months.append(_date(y, m, 1))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    # Pre-compute live repayment totals (non-reversed JE) per loan per month.
    rep_rows = (
        db.query(Repayment, JournalEntry)
        .join(JournalEntry, JournalEntry.id == Repayment.journal_entry_id)
        .filter(
            Repayment.loan_id.in_([L.id for L in loans]),
            JournalEntry.reversed_by.is_(None),
            JournalEntry.reversed_at.is_(None),
        )
        .all()
    )

    # Pre-build a label for each loan ("April 2026 (c11452f2)") so per-month
    # repayment rows are immediately readable to the member.
    def _loan_label(L) -> str:
        short = str(L.id)[:8]
        if L.disbursement_date:
            return f"{L.disbursement_date.strftime('%B %Y')} ({short})"
        return short

    loan_lookup = {L.id: L for L in loans}

    timeline: list[dict] = []
    for month_start in months:
        # Cumulative figures as of end of this month.
        next_month_start = (
            _date(month_start.year + 1, 1, 1)
            if month_start.month == 12
            else _date(month_start.year, month_start.month + 1, 1)
        )

        principal_disbursed = Decimal("0.00")
        interest_accrued = Decimal("0.00")
        loans_this_month: list[dict] = []
        for L in loans:
            if L.disbursement_date >= next_month_start:
                continue  # not yet disbursed at end of this month
            principal_disbursed += L.loan_amount or Decimal("0.00")
            li = (L.loan_amount or Decimal("0.00")) * (L.percentage_interest or Decimal("0.00")) / Decimal("100")
            interest_accrued += li
            if (L.disbursement_date.year, L.disbursement_date.month) == (month_start.year, month_start.month):
                loans_this_month.append({
                    "loan_id": str(L.id),
                    "amount": float(L.loan_amount or 0),
                    "expected_interest": float(li.quantize(Decimal("0.01"))),
                })

        principal_paid = Decimal("0.00")
        interest_paid = Decimal("0.00")
        reps_this_month: list[dict] = []
        for rep, je in rep_rows:
            if rep.repayment_date and rep.repayment_date < next_month_start:
                principal_paid += rep.principal_amount or Decimal("0.00")
                interest_paid += rep.interest_amount or Decimal("0.00")
            # Group by the month the repayment was DATED in (matches the rows
            # the member sees on their statement). Carve-out source_type is
            # set by move_repayment_portion in loan_repair.py.
            if rep.repayment_date and (
                rep.repayment_date.year == month_start.year
                and rep.repayment_date.month == month_start.month
            ):
                src_loan = loan_lookup.get(rep.loan_id)
                was_carved = (je.source_type == "repayment_carve_out")
                reps_this_month.append({
                    "loan_id": str(rep.loan_id),
                    "loan_label": _loan_label(src_loan) if src_loan else str(rep.loan_id)[:8],
                    "date": rep.repayment_date.isoformat(),
                    "principal": float((rep.principal_amount or Decimal("0.00")).quantize(Decimal("0.01"))),
                    "interest": float((rep.interest_amount or Decimal("0.00")).quantize(Decimal("0.01"))),
                    "total": float((rep.total_amount or Decimal("0.00")).quantize(Decimal("0.01"))),
                    "was_carved_out": was_carved,
                    "narration": (je.description or None) if was_carved else None,
                })

        # Sort: carve-out lines after originals; within each, by loan label.
        reps_this_month.sort(key=lambda r: (r["was_carved_out"], r["loan_label"]))

        loan_balance = max(Decimal("0.00"), principal_disbursed - principal_paid)
        interest_balance = max(Decimal("0.00"), interest_accrued - interest_paid)

        timeline.append({
            "month": month_start.isoformat(),
            "loan_balance": float(loan_balance.quantize(Decimal("0.01"))),
            "interest_balance": float(interest_balance.quantize(Decimal("0.01"))),
            "loans_disbursed_this_month": loans_this_month,
            "repayments_this_month": reps_this_month,
        })

    return timeline
