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


CATEGORY_LABEL = {
    "savings": "Savings",
    "social_fund": "Social Fund",
    "admin_fund": "Admin Fund",
    "penalty": "Penalty",
}


def _humanise_note(
    source_type: str | None,
    category: str,
    dealing_month,
    member_name: str,
    signed_amount: float,
    je_description: str | None,
    line_description: str | None,
) -> str:
    """Build a member-facing note for a journal line.

    Designed for Posted Transactions — collapses raw stuff like
    "Deposit approval for member fbe2758f-…" into "May 2026 Savings deposit
    for Simon Mugala". Falls back to the line/JE description for unrecognised
    source types so we never lose information.
    """
    cat = CATEGORY_LABEL.get(category, category.replace("_", " ").title())
    month_label = dealing_month.strftime("%B %Y") if dealing_month else ""
    who = member_name or "member"
    src = (source_type or "").strip()

    if src == "deposit_approval":
        return f"{month_label} — {cat} deposit for {who}".strip(" —")
    if src == "excess_contribution":
        direction = "transfer in" if signed_amount > 0 else "transfer out"
        return f"{month_label} — {cat} excess {direction} for {who}".strip(" —")
    if src == "transaction_split":
        # Prefer the line-level description which already names the target
        # ("Late Loan Application — K150 (split from social fund)" etc.).
        return (line_description or je_description or f"{month_label} — {cat} split").strip()
    if src == "transaction_reverse":
        return (line_description or je_description or f"{month_label} — {cat} reversal").strip()
    if src == "penalty":
        return f"{month_label} — {cat} charged to {who}".strip(" —")
    if src == "penalty_reversal":
        return f"{month_label} — {cat} reversal for {who}".strip(" —")
    if src == "cycle_initial_requirement":
        return f"{month_label} — opening {cat} requirement for {who}".strip(" —")

    # Fallback: prefer line description, then JE description (still better
    # than nothing). UUIDs are stripped for readability.
    import re as _re
    fallback = (line_description or je_description or f"{cat} entry").strip()
    fallback = _re.sub(
        r"\b[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}\b",
        "",
        fallback,
    )
    fallback = _re.sub(r"\s{2,}", " ", fallback).strip(" -—")
    if member_name and member_name not in fallback:
        fallback = f"{fallback} — {member_name}".strip(" —")
    return fallback


def list_member_transactions(db: Session, member_id: UUID) -> dict:
    """Return all non-loan journal lines tied to this member, grouped by
    the parent JournalEntry's dealing_month (the reporting period the entry
    is allocated to, independent of when it was actually posted).
    """
    # Resolve the member's display name once so we can build readable notes
    # ("Joshua Banda — Savings for May 2026") instead of leaking UUIDs in
    # historical JE descriptions like "Deposit approval for member fbe2…".
    from app.models.member import MemberProfile
    from app.models.user import User
    member_name = ""
    prof_row = (
        db.query(MemberProfile, User)
        .join(User, User.id == MemberProfile.user_id)
        .filter(MemberProfile.id == member_id)
        .first()
    )
    if prof_row:
        _prof, _u = prof_row
        member_name = f"{(_u.first_name or '').strip()} {(_u.last_name or '').strip()}".strip()

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
            "note": _humanise_note(
                je.source_type, category, je.dealing_month, member_name, signed_amount,
                je.description, line.description,
            ),
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
    penalty_type_id: UUID | None = None,
) -> dict:
    """Reallocate `amount` from this line's category to `target_category`.

    Posts a single new JournalEntry for the same member with:
        Debit  source category account  by `amount`
        Credit target category account  by `amount`
    The original line is untouched. Balances on both categories shift.

    When the target category is ``penalty`` and ``penalty_type_id`` is provided,
    a paid ``PenaltyRecord`` of that type is also created for the member, and
    the JE description names the penalty type explicitly (e.g. "Penalty —
    Late Loan Application K150") so the books read clearly instead of using
    the generic word "Penalty". This is the supported way to tag a paid
    penalty by type without restructuring the chart of accounts.
    """
    desc = _require_description(description)
    if target_category not in CATEGORIES:
        raise ValueError(f"Invalid target_category: {target_category}")

    line, je, src_account = _load_line_and_entry(db, line_id)
    if je.reversed_by is not None or je.reversed_at is not None:
        raise ValueError("Cannot split a reversed transaction.")

    src_category = _account_category(src_account.account_name)
    # Same-category is only legal for penalty → penalty when a specific
    # penalty type is being attached (the "tag" path below skips the
    # money-moving JE and just creates a PenaltyRecord).
    if src_category == target_category and not (
        src_category == "penalty"
        and target_category == "penalty"
        and penalty_type_id is not None
    ):
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

    # Resolve penalty type (only meaningful when target is penalty).
    from app.models.transaction import PenaltyType, PenaltyRecord, PenaltyRecordStatus
    penalty_type = None
    if penalty_type_id is not None:
        if target_category != "penalty":
            raise ValueError("penalty_type_id is only valid when target_category = 'penalty'")
        penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
        if not penalty_type:
            raise ValueError("penalty_type not found")

    # Build descriptions that name the specific penalty type when present.
    target_label = (
        f"penalty ({penalty_type.name})"
        if penalty_type is not None
        else target_category.replace("_", " ")
    )
    src_label = src_category.replace("_", " ")

    # "Tag" path: source AND target are penalty, plus a specific type is set.
    # No money moves between accounts — we just create a PenaltyRecord linked
    # to the *existing* JE so reports can recognise this K_x as the specific
    # penalty type going forward. Posting a same-account net-zero JE would
    # only clutter the ledger.
    tag_mode = (
        src_category == "penalty"
        and target_category == "penalty"
        and penalty_type is not None
    )

    new_je = None
    if not tag_mode:
        header_desc = (
            f"Split K{amt} from {src_label} → {target_label}: {desc}"
        )[:255]
        src_line_desc = f"Reallocated to {target_label}"[:255]
        if penalty_type is not None:
            target_line_desc = f"{penalty_type.name} — K{amt} (split from {src_label})"[:255]
        else:
            target_line_desc = f"Split in from {src_label}"

        new_je = create_journal_entry(
            db=db,
            description=header_desc,
            dealing_month=je.dealing_month,
            cycle_id=je.cycle_id,
            source_type="transaction_split",
            source_ref=str(line.id),
            lines=[
                {
                    "account_id": src_account.id,
                    "debit_amount": amt,
                    "credit_amount": Decimal("0.00"),
                    "description": src_line_desc,
                },
                {
                    "account_id": target_account.id,
                    "debit_amount": Decimal("0.00"),
                    "credit_amount": amt,
                    "description": target_line_desc,
                },
            ],
            created_by=user_id,
        )

    # Create the paid PenaltyRecord whether we posted a JE or just tagged.
    # In tag mode we link it to the existing JE so the books carry the
    # type-by-type traceability without extra ledger entries.
    penalty_record_id = None
    if penalty_type is not None:
        rec = PenaltyRecord(
            member_id=member_id,
            penalty_type_id=penalty_type.id,
            status=PenaltyRecordStatus.PAID.value,
            created_by=user_id,
            approved_by=user_id,
            approved_at=datetime.now(),
            journal_entry_id=(new_je.id if new_je is not None else je.id),
            notes=(
                (
                    f"Tagged via Posted Transactions — K{amt} penalty entry on "
                    f"{je.dealing_month} assigned to type {penalty_type.name}. {desc}"
                )
                if tag_mode
                else (
                    f"Tagged via Posted Transactions split — "
                    f"K{amt} reallocated from {src_label} on {je.dealing_month}. {desc}"
                )
            )[:1000],
        )
        db.add(rec)
        db.flush()
        penalty_record_id = str(rec.id)

    db.commit()
    return {
        "new_journal_entry_id": str(new_je.id) if new_je is not None else None,
        "tagged_only": tag_mode,
        "amount": float(amt),
        "from_category": src_category,
        "to_category": target_category,
        "penalty_type_id": str(penalty_type.id) if penalty_type else None,
        "penalty_type_name": penalty_type.name if penalty_type else None,
        "penalty_record_id": penalty_record_id,
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
