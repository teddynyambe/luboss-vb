"""Posted-transaction repair operations.

The Reconciliation page's "Posted Transactions" tab exposes per-month, per-
member, **non-loan** ledger lines and lets the treasurer make targeted
corrections without re-running a whole reconciliation. Operations:

  - reverse  : mark the underlying JournalEntry reversed; balance queries
               already filter reversed JEs so the line is effectively removed.
  - split    : reallocate part or all of a line's amount from its category
               to a different category (savings / social_fund / admin_fund /
               penalty), posting a new JE that debits source and credits
               target on member-specific accounts.
  - move     : update the parent JournalEntry's entry_date (and cycle_id) so
               the line falls into a different month. Cannot move into the
               future.

Every action requires a non-empty description (min 5 chars) which lands on
the relevant JE field plus the audit log.

Loan transactions (Loan Disbursement, Loan Repayment principal, Interest)
are deliberately out of scope here — those are managed via the Loan State
panel (Consolidate, Move Repayment, Reverse Repayment, Edit Split).
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, date
from uuid import UUID
from typing import Optional

from sqlalchemy import func, and_, extract
from sqlalchemy.orm import Session

from app.models.transaction import DepositProof
from app.models.ledger import JournalEntry, JournalLine, LedgerAccount, AccountType
from app.models.cycle import Cycle, CycleStatus
from app.services.accounting import create_journal_entry


CATEGORIES = ("savings", "social_fund", "admin_fund", "penalty")
MIN_DESCRIPTION_CHARS = 5


def _account_category(name: str | None) -> str | None:
    """Classify a ledger account by its name. Returns one of CATEGORIES or
    None for accounts we don't manage in Posted Transactions."""
    if not name:
        return None
    n = name.lower()
    if "savings" in n:
        return "savings"
    if "social fund" in n or "social_fund" in n:
        return "social_fund"
    if "admin fund" in n or "admin_fund" in n:
        return "admin_fund"
    if "penalt" in n:
        return "penalty"
    return None  # loans receivable, interest income, bank cash, etc.


def _loan_account_codes_lower() -> set[str]:
    return {"bank_cash"}  # loans/interest handled by the substring filter below


def _is_loan_or_excluded(account: LedgerAccount) -> bool:
    """True if the account is loan-related, bank cash, interest income, or
    something else outside the Posted Transactions scope."""
    code = (account.account_code or "").lower()
    name = (account.account_name or "").lower()
    if code in _loan_account_codes_lower():
        return True
    if code.startswith("loans_receivable") or "loans receivable" in name:
        return True
    if code == "interest_income" or "interest income" in name:
        return True
    return False


def _require_description(description: str | None) -> str:
    txt = (description or "").strip()
    if len(txt) < MIN_DESCRIPTION_CHARS:
        raise ValueError(
            f"A description of at least {MIN_DESCRIPTION_CHARS} characters is required."
        )
    return txt


def _get_member_category_account(
    db: Session, member_id: UUID, category: str
) -> LedgerAccount | None:
    """Look up the per-member ledger account for a given category."""
    name_filter = {
        "savings": "%savings%",
        "social_fund": "%social fund%",
        "admin_fund": "%admin fund%",
        "penalty": "%penalt%",
    }.get(category)
    if not name_filter:
        return None
    return db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike(name_filter),
    ).first()


def list_member_transactions(db: Session, member_id: UUID) -> dict:
    """Return all non-loan journal lines tied to this member, grouped by
    the parent JournalEntry's dealing_month (the reporting period the entry
    is allocated to, independent of when it was actually posted).
    """
    lines = (
        db.query(JournalLine, JournalEntry, LedgerAccount)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .filter(LedgerAccount.member_id == member_id)
        .order_by(JournalEntry.dealing_month.desc(), JournalEntry.entry_date.desc(), JournalEntry.id, JournalLine.id)
        .all()
    )

    # Build a map of (original line id) -> contra JE for fast lookup.
    contra_jes = (
        db.query(JournalEntry)
        .filter(JournalEntry.source_type == "transaction_reverse")
        .all()
    )
    contra_by_line: dict[str, JournalEntry] = {}
    contra_je_ids: set[UUID] = set()
    for c in contra_jes:
        contra_je_ids.add(c.id)
        if c.source_ref:
            contra_by_line[c.source_ref] = c

    months: dict[str, dict] = {}
    today_month = (date.today().year, date.today().month)

    for line, je, acct in lines:
        if _is_loan_or_excluded(acct):
            continue
        category = _account_category(acct.account_name)
        if category is None:
            continue
        # Hide contra JEs' own lines — the reversal is shown as a marker on
        # the original line, not as a separate row.
        if je.id in contra_je_ids:
            continue
        # Group by dealing month (the reporting period this entry is allocated to).
        if not je.dealing_month:
            continue
        m_key = je.dealing_month.strftime("%Y-%m")
        if m_key not in months:
            months[m_key] = {
                "month": m_key,
                "month_label": je.dealing_month.strftime("%B %Y"),
                "lines": [],
                "totals": {c: 0.0 for c in CATEGORIES},
            }
        signed_amount = float((line.credit_amount or Decimal("0.00")) - (line.debit_amount or Decimal("0.00")))
        # A line is "live" iff:
        #   * its parent JE is not reversed (legacy whole-JE reversal), AND
        #   * no per-line contra entry exists pointing at it.
        parent_reversed = je.reversed_by is not None or je.reversed_at is not None
        contra_je = contra_by_line.get(str(line.id))
        contra_active = contra_je is not None and contra_je.reversed_by is None
        is_live = not parent_reversed and not contra_active
        reversal_reason = (
            je.reversal_reason if parent_reversed
            else (contra_je.description if contra_active else None)
        )
        reversed_at = (
            je.reversed_at.isoformat() if parent_reversed and je.reversed_at
            else (contra_je.entry_date.isoformat() if contra_active and contra_je.entry_date else None)
        )
        months[m_key]["lines"].append({
            "id": str(line.id),
            "journal_entry_id": str(je.id),
            "ledger_account_id": str(acct.id),
            "ledger_account_name": acct.account_name,
            "entry_date": je.entry_date.isoformat(),
            "category": category,
            "amount": signed_amount,
            "is_live": is_live,
            "je_description": je.description,
            "je_source_type": je.source_type,
            "reversed_at": reversed_at,
            "reversal_reason": reversal_reason,
            "can_act": is_live,
        })
        if is_live:
            months[m_key]["totals"][category] += signed_amount

    # Sort months desc (most recent first).
    ordered = sorted(
        months.values(),
        key=lambda m: m["month"],
        reverse=True,
    )
    return {
        "member_id": str(member_id),
        "months": ordered,
        "today_month": f"{today_month[0]:04d}-{today_month[1]:02d}",
    }


def _load_line_and_entry(
    db: Session, line_id: UUID
) -> tuple[JournalLine, JournalEntry, LedgerAccount]:
    line = db.query(JournalLine).filter(JournalLine.id == line_id).first()
    if not line:
        raise ValueError("Transaction line not found.")
    je = db.query(JournalEntry).filter(JournalEntry.id == line.journal_entry_id).first()
    if not je:
        raise ValueError("Parent journal entry missing.")
    account = db.query(LedgerAccount).filter(LedgerAccount.id == line.ledger_account_id).first()
    if not account:
        raise ValueError("Ledger account missing for line.")
    if _is_loan_or_excluded(account):
        raise ValueError(
            "Loan-related transactions are managed via the Loan State panel, not here."
        )
    if _account_category(account.account_name) is None:
        raise ValueError("This account category is not editable from Posted Transactions.")
    return line, je, account


def reverse_transaction(
    db: Session,
    line_id: UUID,
    description: str,
    user_id: UUID,
) -> dict:
    """Post a contra journal entry that nets out this single line's effect.

    Per-line semantics — the parent JournalEntry stays live and its OTHER
    lines (e.g. another category in the same deposit) are unaffected. The
    contra JE has two balanced lines: one against the source account and one
    against BANK_CASH (the universal counterparty). It's tagged with
    source_type='transaction_reverse' and source_ref=<line.id> so the list
    endpoint can mark the original line as reversed in the UI.
    """
    desc = _require_description(description)
    line, je, account = _load_line_and_entry(db, line_id)

    # Refuse if the parent JE was already reversed (legacy whole-JE reversal)
    # or if this specific line already has a contra entry.
    if je.reversed_by is not None or je.reversed_at is not None:
        raise ValueError("This transaction's parent journal entry is already reversed.")
    existing_contra = db.query(JournalEntry).filter(
        JournalEntry.source_type == "transaction_reverse",
        JournalEntry.source_ref == str(line.id),
        JournalEntry.reversed_by.is_(None),
    ).first()
    if existing_contra:
        raise ValueError("This transaction line has already been reversed.")

    bank_cash = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "BANK_CASH"
    ).first()
    if not bank_cash:
        raise ValueError("BANK_CASH ledger account not found.")

    credit_amt = line.credit_amount or Decimal("0.00")
    debit_amt = line.debit_amount or Decimal("0.00")
    if credit_amt <= 0 and debit_amt <= 0:
        raise ValueError("Cannot reverse a zero-amount line.")

    if credit_amt > 0:
        # Original was a credit on the member's account → contra debits it
        # and credits BANK_CASH (cash effectively flows back out).
        contra_lines = [
            {"account_id": account.id, "debit_amount": credit_amt,
             "credit_amount": Decimal("0.00"),
             "description": f"Reverse {account.account_name}: {desc[:200]}"},
            {"account_id": bank_cash.id, "debit_amount": Decimal("0.00"),
             "credit_amount": credit_amt,
             "description": "Contra for transaction reverse"},
        ]
    else:
        # Original was a debit on the member's account → contra credits it
        # and debits BANK_CASH.
        contra_lines = [
            {"account_id": account.id, "debit_amount": Decimal("0.00"),
             "credit_amount": debit_amt,
             "description": f"Reverse {account.account_name}: {desc[:200]}"},
            {"account_id": bank_cash.id, "debit_amount": debit_amt,
             "credit_amount": Decimal("0.00"),
             "description": "Contra for transaction reverse"},
        ]

    new_je = create_journal_entry(
        db=db,
        description=f"Reverse of {account.account_name}: {desc}"[:255],
        dealing_month=je.dealing_month,
        cycle_id=je.cycle_id,
        source_type="transaction_reverse",
        source_ref=str(line.id),
        lines=contra_lines,
        created_by=user_id,
    )
    db.commit()
    return {
        "contra_journal_entry_id": str(new_je.id),
        "reversed_line_id": str(line.id),
        "reason": desc,
    }


def split_transaction(
    db: Session,
    line_id: UUID,
    target_category: str,
    amount: Decimal,
    description: str,
    user_id: UUID,
) -> dict:
    """Reallocate `amount` from this line's category to `target_category`.

    Posts a single new JournalEntry for the same member with:
        Debit  source category account  by `amount`
        Credit target category account  by `amount`
    The original line is untouched. Balances on both categories shift.
    """
    desc = _require_description(description)
    if target_category not in CATEGORIES:
        raise ValueError(f"Invalid target_category: {target_category}")

    line, je, src_account = _load_line_and_entry(db, line_id)
    if je.reversed_by is not None or je.reversed_at is not None:
        raise ValueError("Cannot split a reversed transaction.")

    src_category = _account_category(src_account.account_name)
    if src_category == target_category:
        raise ValueError("Target category must differ from the source category.")

    member_id = src_account.member_id
    if not member_id:
        raise ValueError("Source account is not a member account.")

    target_account = _get_member_category_account(db, member_id, target_category)
    if not target_account:
        # The category exists in CATEGORIES but the member doesn't yet have an
        # account for it. Refuse rather than auto-creating from a repair tool.
        raise ValueError(
            f"This member doesn't have a {target_category} ledger account yet. "
            "Have them make a deposit including that category first, then retry."
        )

    amt = Decimal(str(amount))
    if amt <= 0:
        raise ValueError("Split amount must be positive.")
    # Cap by what's actually on the source line (using signed credit amount).
    source_signed = (line.credit_amount or Decimal("0.00")) - (line.debit_amount or Decimal("0.00"))
    if amt > source_signed:
        raise ValueError(
            f"Split amount ({amt}) exceeds this line's current value ({source_signed})."
        )

    new_je = create_journal_entry(
        db=db,
        description=(
            f"Treasurer split {amt} from {src_category} to {target_category}: {desc}"
        )[:255],
        dealing_month=je.dealing_month,
        cycle_id=je.cycle_id,
        source_type="transaction_split",
        source_ref=str(line.id),
        lines=[
            {
                "account_id": src_account.id,
                "debit_amount": amt,
                "credit_amount": Decimal("0.00"),
                "description": f"Split out to {target_category}",
            },
            {
                "account_id": target_account.id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": amt,
                "description": f"Split in from {src_category}",
            },
        ],
        created_by=user_id,
    )
    db.commit()
    return {
        "new_journal_entry_id": str(new_je.id),
        "amount": float(amt),
        "from_category": src_category,
        "to_category": target_category,
        "reason": desc,
    }


def move_transaction(
    db: Session,
    line_id: UUID,
    target_month: str,   # "YYYY-MM"
    description: str,
    user_id: UUID,
) -> dict:
    """Move the parent JournalEntry to a different month. Refuses future months."""
    desc = _require_description(description)
    line, je, account = _load_line_and_entry(db, line_id)
    if je.reversed_by is not None or je.reversed_at is not None:
        raise ValueError("Cannot move a reversed transaction.")

    try:
        y_str, m_str = target_month.split("-")
        target_y = int(y_str)
        target_m = int(m_str)
        target_date = date(target_y, target_m, 1)
    except (ValueError, AttributeError):
        raise ValueError("target_month must be YYYY-MM.")

    today = date.today()
    if (target_y, target_m) > (today.year, today.month):
        raise ValueError("Cannot move a transaction into a future month.")

    # Find a cycle that covers the target month (if cycles are defined).
    new_cycle: Optional[Cycle] = None
    try:
        new_cycle = db.query(Cycle).filter(
            Cycle.start_date <= target_date,
            (Cycle.end_date.is_(None)) | (Cycle.end_date >= target_date),
        ).order_by(Cycle.start_date.desc()).first()
    except Exception:
        new_cycle = None

    # Move the *dealing month* (the reporting bucket) — leave entry_date intact as
    # the immutable audit trail of when the entry was actually posted.
    from app.services.accounting import get_dealing_month_date
    old_dealing = je.dealing_month
    target_cycle_id = new_cycle.id if new_cycle else je.cycle_id
    je.dealing_month = get_dealing_month_date(db, target_cycle_id, target_date)
    if new_cycle:
        je.cycle_id = new_cycle.id

    old_label = old_dealing.strftime('%Y-%m') if old_dealing else 'unknown'
    note = (
        f"[Moved dealing month from {old_label} to {target_month} "
        f"by treasurer: {desc}]"
    )
    je.description = (
        (je.description + " " if je.description else "") + note
    )[:255]
    db.commit()
    return {
        "journal_entry_id": str(je.id),
        "moved_to": target_month,
        "cycle_id": str(je.cycle_id) if je.cycle_id else None,
        "reason": desc,
    }
