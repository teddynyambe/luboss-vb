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
from app.services.accounting import create_journal_entry, get_account_balance, get_dealing_month_date
from app.models.member import MemberProfile
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime
from typing import Optional
import re


def is_cycle_defined_penalty_type(penalty_type_name: str) -> bool:
    """Check if a penalty type name matches cycle-defined penalty types.
    
    Cycle-defined penalties are automatically created by the system:
    - Late Declaration
    - Late Deposits
    - Late Loan Application
    
    These should not be created manually by compliance officers.
    """
    cycle_defined_names = [
        "Late Declaration",
        "Late Deposits",
        "Late Loan Application",
        "late declaration",  # Case variations
        "late deposits",
        "late loan application"
    ]
    return penalty_type_name.strip() in cycle_defined_names or \
           any(name.lower() in penalty_type_name.lower() for name in cycle_defined_names)


def get_system_user_id(db: Session) -> Optional[UUID]:
    """Get a system user ID (admin) for system-generated records.

    Returns the first admin user ID, or None if no admin exists.
    This is used for system-generated penalty records where created_by is required.
    """
    from app.models.user import User, UserRoleEnum
    admin_user = db.query(User).filter(User.role == UserRoleEnum.ADMIN).first()
    return admin_user.id if admin_user else None


def build_late_penalty_narration(
    kind: str,
    effective_month,
    offending_at,
    period_start=None,
    period_end=None,
    monthly_start_day=None,
    monthly_end_day=None,
) -> str:
    """Rich audit narration written into PenaltyRecord.notes for cycle-defined
    (auto-issued) late penalties.

    The output is a single line (may be long) that captures:
      * the penalty kind (keeps 'Late Declaration' / 'Late Deposits' /
        'Late Loan Application' as the leading substring so existing
        duplicate-check ILIKE queries still match)
      * the effective month it belongs to (also kept as a substring so
        duplicate-check queries by "%<month name>%" still match)
      * the EXACT date+time the offending action landed
      * how many days past the cutoff that was
      * the missed window's start/end (dates when known, otherwise days)

    A treasurer or compliance officer reading a penalty record should not
    need to open any other record to justify or dispute the charge — it's
    all there.

    kind:
        Must be one of "Late Declaration", "Late Deposits",
        "Late Loan Application" (matches PenaltyType.name conventions).
    effective_month:
        Date (or datetime) identifying the reporting month the penalty
        belongs to. Used purely for the human label; not the same as the
        cutoff date.
    offending_at:
        Datetime the offending action actually took place — e.g.
        `Declaration.created_at`, `LoanApplication.application_date`,
        `DepositProof.uploaded_at`. Time-of-day is preserved.
    period_start / period_end:
        Optional exact date bounds of the missed window. When set, "days
        late" is computed vs period_end.
    monthly_start_day / monthly_end_day:
        Fallbacks used only for wording when concrete dates aren't
        available.
    """
    from datetime import datetime as _dt, date as _date

    def _fmt_dt(v):
        # Serialise as ISO 8601 UTC ('YYYY-MM-DDTHH:MM:SSZ'). The frontend
        # detects this pattern and rewrites it to the browser's locale so a
        # Zambian treasurer sees CAT while a US auditor sees CDT — the
        # underlying record stays unambiguous either way.
        if not v:
            return "unknown time"
        if isinstance(v, _dt):
            return v.strftime("%Y-%m-%dT%H:%M:%SZ")
        return v.strftime("%Y-%m-%d")

    def _fmt_date(v):
        # Dates render as YYYY-MM-DD — same detection pattern lets the
        # frontend format them in the browser's locale.
        if not v:
            return "unknown date"
        if isinstance(v, _dt):
            v = v.date()
        return v.strftime("%Y-%m-%d")

    if isinstance(effective_month, _dt):
        effective_month = effective_month.date()
    month_label = effective_month.strftime("%B %Y") if effective_month else "unknown month"

    action_label = {
        "Late Declaration":       "the declaration",
        "Late Deposits":          "the deposit",
        "Late Deposit":           "the deposit",
        "Late Loan Application":  "the loan application",
    }.get(kind, "the action")

    days_late = None
    if offending_at and period_end:
        try:
            action_date = offending_at.date() if isinstance(offending_at, _dt) else offending_at
            end_date = period_end.date() if isinstance(period_end, _dt) else period_end
            delta = (action_date - end_date).days
            if delta > 0:
                days_late = delta
        except Exception:
            days_late = None

    days_late_clause = ""
    if days_late is not None:
        days_late_clause = f", {days_late} day{'s' if days_late != 1 else ''} after the cutoff"

    action_at_str = _fmt_dt(offending_at) if offending_at else "an unrecorded time"

    if period_start and period_end:
        window_clause = f" (period: {_fmt_date(period_start)} to {_fmt_date(period_end)})"
    elif period_end:
        window_clause = f" (cutoff: {_fmt_date(period_end)})"
    elif monthly_end_day:
        window_clause = f" (cutoff: day {monthly_end_day} of the effective month)"
    else:
        window_clause = ""

    # Second-person phrasing so a member reading their own record sees
    # ownership clearly; a compliance officer reading it still parses
    # naturally as "the member did this".
    return (
        f"{kind} for {month_label} — You made {action_label} on {action_at_str}"
        f"{days_late_clause}{window_clause}."
    ).strip()


def is_reconciliation_declaration(db: Session, declaration_id) -> bool:
    """Return True when the declaration was created via treasurer
    reconciliation (a `DepositProof` with the "reconciliation" sentinel
    upload_path is linked to it).

    Late-declaration / late-deposit / late-loan-application penalties
    should not fire against records created this way — the treasurer is
    entering the record on behalf of the member for a past month, not
    a live submission missing a deadline.

    The sentinel is set by ``reconcile_declaration_and_post`` in
    `services/transaction_repair.py` (and the older chairman reconcile
    path when a member subsequently uploads on top of a reconciled
    declaration).
    """
    if not declaration_id:
        return False
    proof = (
        db.query(DepositProof)
        .filter(
            DepositProof.declaration_id == declaration_id,
            DepositProof.upload_path == "reconciliation",
        )
        .first()
    )
    return proof is not None


def is_reconciliation_declaration_for_member_month(
    db: Session, member_id, effective_year: int, effective_month_num: int
) -> bool:
    """Same detection as ``is_reconciliation_declaration`` but keyed by
    (member × month) — for penalty sites that don't have a declaration
    row in hand (e.g. late-loan-application on a member × application
    month combination) or that operate before the declaration exists."""
    from sqlalchemy import extract as _extract
    if not member_id:
        return False
    row = (
        db.query(DepositProof)
        .join(Declaration, DepositProof.declaration_id == Declaration.id)
        .filter(
            DepositProof.upload_path == "reconciliation",
            DepositProof.member_id == member_id,
            _extract("year", Declaration.effective_month) == effective_year,
            _extract("month", Declaration.effective_month) == effective_month_num,
        )
        .first()
    )
    return row is not None


_MONTH_NAME_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)


def _extract_effective_month_from_notes(notes: str) -> Optional[date]:
    """Best-effort extraction of a `%B %Y` month name from a legacy penalty
    notes string. Returns the first-of-month date, or None if nothing matches.
    Used by the backfill so we don't misattribute a penalty when multiple
    months appear in the same text (uses the first match)."""
    if not notes:
        return None
    m = _MONTH_NAME_RE.search(notes)
    if not m:
        return None
    from calendar import month_name as _mn
    month_names = {mn.lower(): i for i, mn in enumerate(_mn) if mn}
    idx = month_names.get(m.group(1).lower())
    if not idx:
        return None
    try:
        return date(int(m.group(2)), idx, 1)
    except (TypeError, ValueError):
        return None


def rewrite_legacy_penalty_narration(db: Session, penalty) -> Optional[str]:
    """Rewrite a single PenaltyRecord's notes with the rich narration that
    includes the actual offending timestamp. Returns the new notes on
    success or None if the penalty isn't a cycle-defined type or the
    corresponding offending action can't be found.

    Idempotent — a note that already contains an ISO 8601 UTC token is
    left alone.
    """
    from app.models.transaction import (
        Declaration, DeclarationStatus,
        DepositProof, DepositProofStatus,
        LoanApplication,
        PenaltyRecord, PenaltyType,
    )
    from app.models.cycle import CyclePhase, PhaseType
    from sqlalchemy import extract as _extract, and_ as _and
    import calendar as _cal

    if not penalty or not penalty.penalty_type_id:
        return None
    ptype = db.query(PenaltyType).filter(PenaltyType.id == penalty.penalty_type_id).first()
    if not ptype:
        return None
    ptype_name = (ptype.name or "").strip()
    kind_lower = ptype_name.lower()
    kind: Optional[str] = None
    if "late" in kind_lower and "declaration" in kind_lower:
        kind = "Late Declaration"
    elif "late" in kind_lower and "loan" in kind_lower and "application" in kind_lower:
        kind = "Late Loan Application"
    elif "late" in kind_lower and "deposit" in kind_lower:
        kind = "Late Deposits"
    else:
        return None  # not a cycle-defined kind we know how to backfill

    # Skip if the note already carries an ISO timestamp — the rich
    # narration has already been applied.
    if penalty.notes and re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", penalty.notes):
        return None

    effective_month = _extract_effective_month_from_notes(penalty.notes or "")
    if not effective_month:
        # Fall back to date_issued's month if the notes don't reveal it.
        if penalty.date_issued:
            effective_month = date(penalty.date_issued.year, penalty.date_issued.month, 1)
        else:
            return None

    offending_at = None
    period_start = None
    period_end = None

    if kind == "Late Declaration":
        # Look up the member's declaration for the effective month.
        decl = db.query(Declaration).filter(
            Declaration.member_id == penalty.member_id,
            _extract("year", Declaration.effective_month) == effective_month.year,
            _extract("month", Declaration.effective_month) == effective_month.month,
        ).order_by(Declaration.created_at.asc()).first()
        offending_at = getattr(decl, "created_at", None) if decl else None
        # Phase window — look up the CyclePhase for the declaration's cycle.
        cycle_id = decl.cycle_id if decl else None
        if cycle_id:
            phase = db.query(CyclePhase).filter(
                CyclePhase.cycle_id == cycle_id,
                CyclePhase.phase_type == PhaseType.DECLARATION,
            ).first()
            if phase and phase.monthly_end_day:
                try:
                    _, last_day = _cal.monthrange(effective_month.year, effective_month.month)
                    period_end = date(
                        effective_month.year,
                        effective_month.month,
                        min(int(phase.monthly_end_day), last_day),
                    )
                except Exception:
                    period_end = None
            if phase and phase.monthly_start_day:
                try:
                    _s = int(phase.monthly_start_day)
                    if period_end and _s > int(phase.monthly_end_day):
                        prev_month = effective_month.month - 1 or 12
                        prev_year = effective_month.year - (1 if effective_month.month == 1 else 0)
                        _, prev_last = _cal.monthrange(prev_year, prev_month)
                        period_start = date(prev_year, prev_month, min(_s, prev_last))
                    else:
                        period_start = date(effective_month.year, effective_month.month, _s)
                except Exception:
                    period_start = None

    elif kind == "Late Loan Application":
        loan_app = db.query(LoanApplication).filter(
            LoanApplication.member_id == penalty.member_id,
            _extract("year", LoanApplication.application_date) == effective_month.year,
            _extract("month", LoanApplication.application_date) == effective_month.month,
        ).order_by(LoanApplication.application_date.asc()).first()
        offending_at = getattr(loan_app, "application_date", None) if loan_app else None
        cycle_id = loan_app.cycle_id if loan_app else None
        if cycle_id:
            phase = db.query(CyclePhase).filter(
                CyclePhase.cycle_id == cycle_id,
                CyclePhase.phase_type == PhaseType.LOAN_APPLICATION,
            ).first()
            if phase and phase.monthly_end_day:
                try:
                    _, last_day = _cal.monthrange(effective_month.year, effective_month.month)
                    period_end = date(
                        effective_month.year,
                        effective_month.month,
                        min(int(phase.monthly_end_day), last_day),
                    )
                except Exception:
                    period_end = None
            if phase and phase.monthly_start_day:
                try:
                    period_start = date(
                        effective_month.year, effective_month.month, int(phase.monthly_start_day),
                    )
                except Exception:
                    period_start = None

    else:  # Late Deposits
        # Deposit period ENDS in the next month; effective_month is the
        # declaration's effective month. Find the DepositProof whose
        # declaration was for that month.
        deposit = db.query(DepositProof).join(
            Declaration, DepositProof.declaration_id == Declaration.id,
        ).filter(
            DepositProof.member_id == penalty.member_id,
            _extract("year", Declaration.effective_month) == effective_month.year,
            _extract("month", Declaration.effective_month) == effective_month.month,
        ).order_by(DepositProof.uploaded_at.asc()).first()
        offending_at = getattr(deposit, "uploaded_at", None) if deposit else None
        cycle_id = deposit.cycle_id if deposit else None
        if cycle_id:
            phase = db.query(CyclePhase).filter(
                CyclePhase.cycle_id == cycle_id,
                CyclePhase.phase_type == PhaseType.DEPOSITS,
            ).first()
            if phase and phase.monthly_end_day:
                try:
                    next_year = effective_month.year + (1 if effective_month.month == 12 else 0)
                    next_month = 1 if effective_month.month == 12 else effective_month.month + 1
                    _, last_day = _cal.monthrange(next_year, next_month)
                    period_end = date(next_year, next_month, min(int(phase.monthly_end_day), last_day))
                except Exception:
                    period_end = None
            if phase and phase.monthly_start_day:
                try:
                    period_start = date(
                        effective_month.year, effective_month.month, int(phase.monthly_start_day),
                    )
                except Exception:
                    period_start = None

    # Fallback: no linked action row found → keep at least the issued
    # timestamp so the narration still has SOME time reference.
    if offending_at is None:
        offending_at = penalty.date_issued

    new_notes = build_late_penalty_narration(
        kind=kind,
        effective_month=effective_month,
        offending_at=offending_at,
        period_start=period_start,
        period_end=period_end,
    )
    penalty.notes = new_notes
    return new_notes


def backfill_penalty_narrations(db: Session, dry_run: bool = False) -> dict:
    """Sweep every PenaltyRecord and rewrite legacy notes for cycle-defined
    types. Idempotent — records already carrying an ISO 8601 UTC token in
    their notes are skipped.

    Returns a summary: ``{scanned, rewritten, skipped, by_kind}``.
    """
    from app.models.transaction import PenaltyRecord

    scanned = 0
    rewritten = 0
    skipped = 0
    by_kind: dict = {"Late Declaration": 0, "Late Deposits": 0, "Late Loan Application": 0}

    penalties = db.query(PenaltyRecord).all()
    for p in penalties:
        scanned += 1
        new_notes = rewrite_legacy_penalty_narration(db, p)
        if new_notes is None:
            skipped += 1
            continue
        # Bump the by-kind counter based on the leading token of the new
        # narration ("Late Declaration for June 2026 — …").
        for k in by_kind:
            if new_notes.startswith(k):
                by_kind[k] += 1
                break
        rewritten += 1

    if not dry_run and rewritten > 0:
        db.commit()
    elif dry_run:
        db.rollback()

    return {
        "scanned": scanned,
        "rewritten": rewritten,
        "skipped": skipped,
        "by_kind": by_kind,
        "dry_run": dry_run,
    }


def reverse_penalties_for_reconciliation_declarations(
    db: Session, actor_user_id: UUID, dry_run: bool = False
) -> dict:
    """Sweep every live cycle-defined penalty (Late Declaration / Late
    Deposits / Late Loan Application) and reverse the ones tied to
    declarations that were created via treasurer reconciliation. These
    penalties were charged in error under the old code path — the
    treasurer's retrospective bookkeeping shouldn't have generated a
    late fee against the member.

    For each matching penalty:
      * `status` flips to REVERSED (from APPROVED / PAID / REVERSAL_PENDING).
      * `reversed_by / reversed_at / reversal_reason` are stamped.
      * If a live ledger JE backed the penalty, a mirror-reversing JE is
        posted (Cr MEM_SAV / Dr PENALTY_INCOME), the original JE is
        marked reversed, and `reversal_journal_entry_id` is linked.

    Idempotent. Runs safely against production; returns a summary. Uses
    the existing `is_reconciliation_declaration` helper as the ground
    truth so it agrees with the guards on the auto-issue sites.
    """
    from app.models.ledger import JournalEntry, JournalLine

    reversible_statuses = {
        PenaltyRecordStatus.APPROVED.value,
        PenaltyRecordStatus.PAID.value,
        PenaltyRecordStatus.REVERSAL_PENDING.value,
    }

    penalties = db.query(PenaltyRecord).filter(
        PenaltyRecord.status.in_(list(reversible_statuses))
    ).all()

    scanned = 0
    reversed_count = 0
    skipped_not_cycle = 0
    skipped_not_reconciled = 0
    skipped_no_link = 0
    reversed_ids = []

    for p in penalties:
        scanned += 1
        ptype = p.penalty_type
        ptype_name = (ptype.name if ptype else "") or ""
        k_lower = ptype_name.strip().lower()
        # Only touch cycle-defined kinds; manual compliance-created
        # penalties are unrelated to reconciliation.
        if not (
            ("late" in k_lower and "declaration" in k_lower)
            or ("late" in k_lower and "deposit" in k_lower)
            or ("late" in k_lower and "loan" in k_lower and "application" in k_lower)
        ):
            skipped_not_cycle += 1
            continue

        # Match the penalty back to the effective month it fired for.
        # Late Declaration / Late Deposits reference the declaration
        # month; Late Loan Application references the application month.
        effective_month = _extract_effective_month_from_notes(p.notes or "")
        if not effective_month and p.date_issued:
            effective_month = date(p.date_issued.year, p.date_issued.month, 1)
        if not effective_month:
            skipped_no_link += 1
            continue

        if not is_reconciliation_declaration_for_member_month(
            db, p.member_id, effective_month.year, effective_month.month
        ):
            skipped_not_reconciled += 1
            continue

        reason = (
            f"Auto-reversed by reconciliation-penalty sweep — the declaration for "
            f"{effective_month.strftime('%B %Y')} was created via treasurer "
            f"reconciliation, so no late-window penalty should have been charged."
        )
        reversal_je_id = None
        if p.journal_entry_id:
            orig_je = db.query(JournalEntry).filter(JournalEntry.id == p.journal_entry_id).first()
            if orig_je and not orig_je.reversed_by:
                orig_lines = db.query(JournalLine).filter(
                    JournalLine.journal_entry_id == orig_je.id
                ).all()
                rev_lines = [
                    {
                        "account_id": ln.ledger_account_id,
                        "debit_amount": ln.credit_amount,
                        "credit_amount": ln.debit_amount,
                        "description": f"Reversal: {ln.description or ''}",
                    }
                    for ln in orig_lines
                ]
                rev_je = create_journal_entry(
                    db=db,
                    description=(
                        f"Penalty auto-reversal — {ptype_name} was wrongly charged on a "
                        f"reconciliation-created declaration ({effective_month.strftime('%B %Y')})"
                    ),
                    lines=rev_lines,
                    dealing_month=orig_je.dealing_month,
                    cycle_id=orig_je.cycle_id,
                    source_ref=str(p.id),
                    source_type="penalty_reversal",
                    created_by=actor_user_id,
                )
                orig_je.reversed_by = actor_user_id
                orig_je.reversed_at = datetime.utcnow()
                orig_je.reversal_reason = reason
                reversal_je_id = rev_je.id

        p.status = PenaltyRecordStatus.REVERSED.value
        p.reversed_by = actor_user_id
        p.reversed_at = datetime.utcnow()
        p.reversal_reason = reason
        if reversal_je_id:
            p.reversal_journal_entry_id = reversal_je_id
        reversed_count += 1
        reversed_ids.append(str(p.id))

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "scanned": scanned,
        "reversed": reversed_count,
        "skipped_not_cycle_defined": skipped_not_cycle,
        "skipped_not_reconciled": skipped_not_reconciled,
        "skipped_no_link": skipped_no_link,
        "reversed_penalty_ids": reversed_ids,
        "dry_run": dry_run,
    }


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
    # Ensure UUID objects — callers may pass strings
    if isinstance(member_id, str):
        member_id = UUID(member_id)
    if isinstance(cycle_id, str):
        cycle_id = UUID(cycle_id)
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
                        dealing_month=get_dealing_month_date(db, cycle_id, effective_month),
                        cycle_id=cycle_id,
                        source_type="cycle_initial_requirement",
                        created_by=None  # System-generated
                    )
    
    # Check if declaration is late and create automatic penalty record
    from app.models.cycle import CyclePhase, PhaseType
    from datetime import date as date_type
    import logging
    
    logger = logging.getLogger(__name__)
    
    declaration_phase = db.query(CyclePhase).filter(
        CyclePhase.cycle_id == cycle_id,
        CyclePhase.phase_type == PhaseType.DECLARATION
    ).first()
    
    if declaration_phase:
        auto_apply = getattr(declaration_phase, 'auto_apply_penalty', False)
        monthly_end_day = getattr(declaration_phase, 'monthly_end_day', None)
        penalty_type_id = getattr(declaration_phase, 'penalty_type_id', None)
        
        logger.info(f"Late declaration penalty check: auto_apply={auto_apply}, monthly_end_day={monthly_end_day}, penalty_type_id={penalty_type_id}")
        
        if auto_apply and monthly_end_day and penalty_type_id:
            today = date_type.today()
            is_late = False

            # Skip when the declaration was created via treasurer
            # reconciliation — the treasurer is entering the record on
            # behalf of the member for a past month; the member didn't
            # miss a live submission window and shouldn't be charged.
            if is_reconciliation_declaration(db, declaration.id):
                logger.info(
                    "Declaration %s was created via reconciliation — skipping late-declaration penalty check",
                    declaration.id,
                )
                # Fall through with is_late=False below.
                pass
            # Check if declaration is late (after monthly_end_day)
            elif today.year == effective_month.year and today.month == effective_month.month:
                if today.day > monthly_end_day:
                    is_late = True
                    logger.info(f"Declaration is late: today.day ({today.day}) > monthly_end_day ({monthly_end_day})")
                else:
                    logger.info(f"Declaration is NOT late: today.day ({today.day}) <= monthly_end_day ({monthly_end_day})")
            elif today.year > effective_month.year or (today.year == effective_month.year and today.month > effective_month.month):
                is_late = True
                logger.info(f"Declaration is late: past month (today={today}, effective_month={effective_month})")
            else:
                logger.info(f"Declaration is NOT late: future month (today={today}, effective_month={effective_month})")
            
            if is_late:
                logger.info(f"Creating late declaration penalty for member {member_id}, effective_month={effective_month}")
                # Get penalty type
                penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty_type_id).first()
                if penalty_type:
                    # Check if penalty record already exists for this declaration
                    # More comprehensive duplicate check: check by member, penalty_type, and effective month
                    # This prevents duplicates even if called multiple times
                    from sqlalchemy import extract, or_, and_
                    existing_penalty = db.query(PenaltyRecord).filter(
                        PenaltyRecord.member_id == member_id,
                        PenaltyRecord.penalty_type_id == penalty_type_id,
                        or_(
                            # Check by date_issued year/month (if created in same month)
                            and_(
                                extract('year', PenaltyRecord.date_issued) == effective_month.year,
                                extract('month', PenaltyRecord.date_issued) == effective_month.month
                            ),
                            # Check by notes containing the effective month (case-insensitive)
                            PenaltyRecord.notes.ilike(f"%{effective_month.strftime('%B %Y')}%"),
                            PenaltyRecord.notes.ilike(f"%{effective_month.strftime('%b %Y')}%")  # Also check abbreviated month
                        )
                    ).first()
                    
                    if not existing_penalty:
                        # Get system user for system-generated penalties
                        system_user_id = get_system_user_id(db)
                        if not system_user_id:
                            # If no admin exists, skip penalty creation (shouldn't happen in production)
                            logger.warning(f"No admin user found to create system penalty for member {member_id}")
                        else:
                            # Get or create member's savings account (needed for posting penalty to ledger)
                            member_savings = db.query(LedgerAccount).filter(
                                LedgerAccount.member_id == member_id,
                                LedgerAccount.account_name.ilike("%savings%")
                            ).first()
                            
                            if not member_savings:
                                # Create savings account if it doesn't exist
                                short_id = str(member_id).replace('-', '')[:8]
                                member_savings = LedgerAccount(
                                    account_code=f"MEM_SAV_{short_id}",
                                    account_name=f"Member Savings - {member_id}",
                                    account_type=AccountType.LIABILITY,
                                    member_id=member_id,
                                    description=f"Savings account for member {member_id}"
                                )
                                db.add(member_savings)
                                db.flush()
                                logger.info(f"Created member savings account for late declaration penalty: {member_savings.id}")
                            
                            # Get penalty income account
                            penalty_income = db.query(LedgerAccount).filter(
                                LedgerAccount.account_code == "PENALTY_INCOME"
                            ).first()
                            
                            if not penalty_income:
                                logger.warning(f"PENALTY_INCOME account not found, cannot post late declaration penalty to ledger")
                            else:
                                # Rich audit narration — captures the exact
                                # timestamp of the offending action + the
                                # window it missed so the treasurer can
                                # justify or dispute later without cross-
                                # referencing other records.
                                _decl_start_day = getattr(declaration_phase, "monthly_start_day", None)
                                _decl_start_date = None
                                _decl_end_date = date_type(
                                    effective_month.year,
                                    effective_month.month,
                                    min(monthly_end_day, 28),  # 28 = safe upper bound for all months
                                )
                                # Guard against monthly_end_day > actual days in month.
                                try:
                                    import calendar as _cal
                                    _, _last_day = _cal.monthrange(effective_month.year, effective_month.month)
                                    _decl_end_date = date_type(
                                        effective_month.year,
                                        effective_month.month,
                                        min(monthly_end_day, _last_day),
                                    )
                                except Exception:
                                    pass
                                if _decl_start_day:
                                    # Declaration windows typically start in the
                                    # PRIOR month (e.g. 15 May → 25 Jun). If the
                                    # start day > end day it must have wrapped
                                    # back to the prior month.
                                    if _decl_start_day > monthly_end_day:
                                        _prev_month = effective_month.month - 1 or 12
                                        _prev_year = effective_month.year - (1 if effective_month.month == 1 else 0)
                                        try:
                                            import calendar as _cal
                                            _, _prev_last = _cal.monthrange(_prev_year, _prev_month)
                                            _decl_start_date = date_type(
                                                _prev_year, _prev_month, min(_decl_start_day, _prev_last),
                                            )
                                        except Exception:
                                            _decl_start_date = None
                                    else:
                                        try:
                                            _decl_start_date = date_type(
                                                effective_month.year,
                                                effective_month.month,
                                                _decl_start_day,
                                            )
                                        except Exception:
                                            _decl_start_date = None
                                _decl_offending_at = getattr(declaration, "created_at", None) or datetime.utcnow()
                                _narration = build_late_penalty_narration(
                                    kind="Late Declaration",
                                    effective_month=effective_month,
                                    offending_at=_decl_offending_at,
                                    period_start=_decl_start_date,
                                    period_end=_decl_end_date,
                                    monthly_start_day=_decl_start_day,
                                    monthly_end_day=monthly_end_day,
                                )

                                # Create PenaltyRecord with APPROVED status (cycle-defined penalties are auto-approved)
                                late_penalty = PenaltyRecord(
                                    member_id=member_id,
                                    penalty_type_id=penalty_type_id,
                                    status=PenaltyRecordStatus.APPROVED.value,  # Use .value to ensure lowercase string is sent
                                    created_by=system_user_id,  # Use admin user for system-generated penalties
                                    notes=_narration,
                                )
                                db.add(late_penalty)
                                db.flush()
                                
                                # Post penalty to ledger immediately (since it's auto-approved)
                                journal_entry = create_journal_entry(
                                    db=db,
                                    description=f"Late declaration penalty for member {member_id}",
                                    lines=[
                                        {
                                            "account_id": member_savings.id,
                                            "debit_amount": penalty_type.fee_amount,
                                            "credit_amount": Decimal("0.00"),
                                            "description": "Late declaration penalty charged to member"
                                        },
                                        {
                                            "account_id": penalty_income.id,
                                            "debit_amount": Decimal("0.00"),
                                            "credit_amount": penalty_type.fee_amount,
                                            "description": "Penalty income"
                                        }
                                    ],
                                    dealing_month=get_dealing_month_date(db, cycle_id, effective_month),
                                    source_ref=str(late_penalty.id),
                                    source_type="penalty",
                                    created_by=system_user_id
                                )
                                
                                # Link journal entry to penalty record
                                late_penalty.journal_entry_id = journal_entry.id
                                late_penalty.approved_by = system_user_id
                                late_penalty.approved_at = datetime.utcnow()
                                
                                logger.info(f"✅ Created late declaration penalty: {late_penalty.id} and posted to ledger: {journal_entry.id}")
                    else:
                        logger.info(f"Penalty already exists for this declaration, skipping creation")
            else:
                logger.info(f"Declaration is not late, no penalty created")
        else:
            missing = []
            if not auto_apply:
                missing.append("auto_apply_penalty=False")
            if not monthly_end_day:
                missing.append("monthly_end_day not set")
            if not penalty_type_id:
                missing.append("penalty_type_id not set")
            logger.warning(f"Late declaration penalty not configured: {', '.join(missing)}")
    else:
        logger.warning(f"No declaration phase found for cycle {cycle_id}")
    
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
    # Ensure UUID objects — callers may pass strings
    if isinstance(declaration_id, str):
        declaration_id = UUID(declaration_id)
    if isinstance(member_id, str):
        member_id = UUID(member_id)
    if isinstance(cycle_id, str):
        cycle_id = UUID(cycle_id)
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
        # When editing after rejection / for a previously-approved declaration with
        # a rejected proof, allow editing regardless of date. Status must be PENDING,
        # APPROVED, or REJECTED — a REJECTED declaration is exactly what the member
        # should be able to revise from a past month.
        if declaration.status not in [
            DeclarationStatus.PENDING,
            DeclarationStatus.APPROVED,
            DeclarationStatus.REJECTED,
        ]:
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
    from app.models.ledger import JournalEntry
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
    # The deposit amount should equal the sum of all components
    # Bank cash is debited for the full amount (cash received)
    # We then credit various accounts to balance
    
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
    
    # Handle Social Fund payment
    # When member pays social fund:
    # 1. Debit member's social fund account (accumulates payments for display)
    # 2. Credit organization receivable (reduces receivable - balances the member debit)
    # Note: Bank cash is already debited above for the full deposit amount
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
            # Credit member account (payment reduces balance due)
            # Required amount → Debit, Payment → Credit, Balance = Debits - Credits
            lines.append({
                "account_id": member_social_fund_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": social_fund,
                "description": "Social fund payment"
            })
            # Note: Organization receivable is a contra account and doesn't need to be adjusted here
            # The member account credit balances with the bank cash debit
    
    # Handle Admin Fund payment
    # Same logic as social fund
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
            # Credit member account (payment reduces balance due)
            # Required amount → Debit, Payment → Credit, Balance = Debits - Credits
            lines.append({
                "account_id": member_admin_fund_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": admin_fund,
                "description": "Admin fund payment"
            })
            # Note: Organization receivable is a contra account and doesn't need to be adjusted here
            # The member account credit balances with the bank cash debit
    
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
    
    # Interest payment draws down INTEREST_RECEIVABLE (the revenue was
    # recognised in INTEREST_INCOME at loan origination, not here).
    # Fallback: if INTEREST_RECEIVABLE doesn't exist (pre-accrual data /
    # dev env without migration), keep the legacy behaviour of crediting
    # INTEREST_INCOME — the ledger stays balanced either way and a warning
    # is logged so the operator can run the seed migration.
    if interest_on_loan > 0:
        from app.models.ledger import LedgerAccount as _LA
        interest_receivable = db.query(_LA).filter(
            _LA.account_code == "INTEREST_RECEIVABLE"
        ).first()
        if interest_receivable:
            lines.append({
                "account_id": interest_receivable.id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": interest_on_loan,
                "description": "Interest collected — draws down receivable"
            })
        elif interest_income_account_id:
            import logging
            logging.getLogger(__name__).warning(
                "approve_deposit: INTEREST_RECEIVABLE missing; falling back to "
                "legacy INTEREST_INCOME credit on deposit %s. Run migration "
                "b8c9d0e1f2a3 to enable accrual-at-origination.", deposit.id,
            )
            lines.append({
                "account_id": interest_income_account_id,
                "debit_amount": Decimal("0.00"),
                "credit_amount": interest_on_loan,
                "description": "Interest on loan payment (legacy — no receivable account)"
            })
    
    if loan_repayment > 0 and loans_receivable_account_id:
        # Credit loan receivable (reduces the receivable balance)
        lines.append({
            "account_id": loans_receivable_account_id,
            "debit_amount": Decimal("0.00"),
            "credit_amount": loan_repayment,
            "description": "Loan principal repayment"
        })
    
    # Log all journal lines before creating entry
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"=== JOURNAL ENTRY LINES FOR DEPOSIT APPROVAL ===")
    logger.info(f"Deposit ID: {deposit.id}, Amount: {deposit.amount}")
    logger.info(f"Declaration: {declaration.effective_month}")
    logger.info(f"Savings: {savings_amount}, Social: {social_fund}, Admin: {admin_fund}")
    logger.info(f"Penalties: {penalties}, Interest: {interest_on_loan}, Repayment: {loan_repayment}")
    
    total_debits = sum(Decimal(str(line.get("debit_amount", 0))) for line in lines)
    total_credits = sum(Decimal(str(line.get("credit_amount", 0))) for line in lines)
    logger.info(f"Total Debits: {total_debits}, Total Credits: {total_credits}, Difference: {total_debits - total_credits}")
    
    for i, line in enumerate(lines):
        logger.info(f"Line {i+1}: Account={line.get('account_id')}, "
                   f"Debit={line.get('debit_amount', 0)}, "
                   f"Credit={line.get('credit_amount', 0)}, "
                   f"Desc={line.get('description', 'N/A')}")
    logger.info(f"=== END JOURNAL ENTRY LINES ===")
    
    # Create journal entry — dealing_month follows the declaration's effective month,
    # NOT the approval timestamp, so deposits approved in a later month are still
    # bucketed under the period they were declared for.
    # Resolve the member's display name once for the description (UUIDs are
    # noise in audit logs and the Posted Transactions feed). Falls back to a
    # short member_id stub if there's no profile/user (shouldn't happen in
    # practice).
    _member_label = str(deposit.member_id)[:8]
    try:
        from app.models.member import MemberProfile as _MP
        from app.models.user import User as _U
        _row = (
            db.query(_MP, _U)
            .join(_U, _U.id == _MP.user_id)
            .filter(_MP.id == deposit.member_id)
            .first()
        )
        if _row:
            _prof, _u = _row
            _name = f"{(_u.first_name or '').strip()} {(_u.last_name or '').strip()}".strip()
            if _name:
                _member_label = _name
    except Exception:
        pass
    _month_label = declaration.effective_month.strftime("%B %Y")
    journal_entry = create_journal_entry(
        db=db,
        description=f"{_month_label} deposit for {_member_label}",
        lines=lines,
        dealing_month=get_dealing_month_date(db, deposit.cycle_id, declaration.effective_month),
        cycle_id=deposit.cycle_id,
        source_ref=str(deposit.id),
        source_type="deposit_approval",
        created_by=approved_by
    )
    
    # Approval record — upsert rather than blind insert. A DepositApproval row
    # may still exist from a previous approval that was later reversed (via
    # reject_declaration / reverse_repayment), or because someone hand-edited
    # the DB and left a stale row whose JE wasn't properly reversed. The
    # unique constraint on deposit_proof_id means we can't just INSERT in
    # either case. Updating in place keeps the row id stable for audit.
    existing_approval = db.query(DepositApproval).filter(
        DepositApproval.deposit_proof_id == deposit.id
    ).first()
    if existing_approval:
        old_je = db.query(JournalEntry).filter(
            JournalEntry.id == existing_approval.journal_entry_id
        ).first() if existing_approval.journal_entry_id else None
        if old_je and old_je.reversed_by is None and old_je.reversed_at is None:
            # Old JE was never reversed. Auto-reverse it now so the ledger
            # doesn't double-count when we point the approval at the new JE.
            import logging
            logging.getLogger(__name__).warning(
                "approve_deposit: prior DepositApproval %s pointed at a live JE %s "
                "for deposit %s; auto-reversing the old JE before re-approving.",
                existing_approval.id, old_je.id, deposit.id,
            )
            old_je.reversed_by = approved_by
            old_je.reversed_at = datetime.utcnow()
        existing_approval.journal_entry_id = journal_entry.id
        existing_approval.approved_by = approved_by
        approval = existing_approval
    else:
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
    
    # Create Repayment record so that get_current_loan() / get_member_loan_balance()
    # can compute outstanding balance and paid totals from Repayment rows.
    # The journal lines above already post to the ledger; this record is the
    # source of truth for principal-vs-interest tracking on the Loan object.
    if loan_repayment > Decimal("0.00") or interest_on_loan > Decimal("0.00"):
        target_loan = (
            db.query(Loan)
            .filter(
                Loan.member_id == deposit.member_id,
                Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED]),
            )
            .order_by(Loan.created_at.asc())  # oldest active loan first
            .first()
        )

        # Reconciliation fallback: if no active loan exists but the declaration
        # has a loan repayment, the declaration is almost certainly historical
        # (a closed loan re-approved after the fact). Attach to the most
        # recently disbursed closed loan whose disbursement_date is on or
        # before this declaration's effective month — that's the loan this
        # payment was always meant for. Without this, the K4k credit lands on
        # the ledger (LOANS_RECEIVABLE) but no Repayment row is created and
        # Loan State shows a phantom outstanding balance.
        if target_loan is None:
            target_loan = (
                db.query(Loan)
                .filter(
                    Loan.member_id == deposit.member_id,
                    Loan.loan_status == LoanStatus.CLOSED,
                    Loan.disbursement_date <= declaration.effective_month,
                )
                .order_by(Loan.disbursement_date.desc(), Loan.created_at.desc())
                .first()
            )

        if target_loan:
            repayment_record = Repayment(
                loan_id=target_loan.id,
                repayment_date=declaration.effective_month,
                principal_amount=loan_repayment,
                interest_amount=interest_on_loan,
                total_amount=loan_repayment + interest_on_loan,
                journal_entry_id=journal_entry.id,
            )
            db.add(repayment_record)

    # Mark penalties as PAID when deposit is approved
    # Find all APPROVED penalty records for this member that match the declared penalty amount
    if penalties > 0:
        # Get all APPROVED penalties for this member
        approved_penalties = db.query(PenaltyRecord).filter(
            PenaltyRecord.member_id == deposit.member_id,
            PenaltyRecord.status == PenaltyRecordStatus.APPROVED
        ).order_by(PenaltyRecord.date_issued.asc()).all()
        
        # Match penalties to the declared amount
        remaining_penalty_amount = penalties
        for penalty in approved_penalties:
            if remaining_penalty_amount <= Decimal("0.00"):
                break
            
            penalty_type = penalty.penalty_type
            if not penalty_type:
                continue
            
            penalty_amount = penalty_type.fee_amount or Decimal("0.00")
            
            # If this penalty amount fits in the remaining amount, mark it as paid
            if penalty_amount <= remaining_penalty_amount:
                penalty.status = PenaltyRecordStatus.PAID.value  # Use .value to ensure lowercase string is sent
                remaining_penalty_amount -= penalty_amount
            # If partial payment, we could handle it here, but for now we'll only mark complete payments
    
    db.commit()
    db.refresh(approval)
    return approval


def post_excess_contributions(
    db: Session,
    member_id: UUID,
    cycle,               # Cycle model instance — carries social/admin fund required
    effective_month,     # date — used to backdate the journal entry
    approved_by: UUID,
) -> dict:
    """
    After a deposit is approved, detect if the member has overpaid Social Fund
    or Admin Fund vs the cycle annual requirement.  For each fund with an excess,
    create a journal entry that reclassifies the excess to the member's savings
    account, backdated to effective_month.

    Idempotent: 'already_transferred' is computed from prior excess_contribution
    debits on the fund account, so running twice will not double-transfer.

    Returns {'social_excess': Decimal, 'admin_excess': Decimal}.
    """
    from app.models.ledger import LedgerAccount, JournalLine, JournalEntry
    from app.services.accounting import create_journal_entry
    from sqlalchemy import func
    from datetime import datetime as dt

    result = {'social_excess': Decimal("0.00"), 'admin_excess': Decimal("0.00")}

    # Look up member's savings account (must exist — created by approve_deposit)
    savings_account = db.query(LedgerAccount).filter(
        LedgerAccount.member_id == member_id,
        LedgerAccount.account_name.ilike("%savings%")
    ).first()
    if not savings_account:
        return result

    for fund_key, required, name_pattern, label in [
        ("social", cycle.social_fund_required, "%social fund%", "Social Fund"),
        ("admin",  cycle.admin_fund_required,  "%admin fund%",  "Admin Fund"),
    ]:
        if not required:
            continue

        fund_account = db.query(LedgerAccount).filter(
            LedgerAccount.member_id == member_id,
            LedgerAccount.account_name.ilike(name_pattern)
        ).first()
        if not fund_account:
            continue

        # Total paid by member (credits from deposit_approval entries)
        total_paid = db.query(func.sum(JournalLine.credit_amount)).join(JournalEntry).filter(
            JournalLine.ledger_account_id == fund_account.id,
            JournalEntry.reversed_by.is_(None),
            JournalEntry.source_type == "deposit_approval",
            JournalLine.credit_amount > 0
        ).scalar() or Decimal("0.00")

        # Already transferred in prior runs (debits from excess_contribution entries)
        already_transferred = db.query(func.sum(JournalLine.debit_amount)).join(JournalEntry).filter(
            JournalLine.ledger_account_id == fund_account.id,
            JournalEntry.reversed_by.is_(None),
            JournalEntry.source_type == "excess_contribution",
            JournalLine.debit_amount > 0
        ).scalar() or Decimal("0.00")

        net_excess = total_paid - Decimal(str(required)) - already_transferred
        if net_excess <= Decimal("0.01"):
            continue

        month_label = effective_month.strftime("%B %Y")
        je = create_journal_entry(
            db=db,
            description=(
                f"Excess {label} contribution K{net_excess:.2f} transferred to savings"
                f" — {month_label}"
            ),
            dealing_month=get_dealing_month_date(db, cycle.id, effective_month),
            source_type="excess_contribution",
            source_ref=str(member_id),
            lines=[
                {
                    "account_id": fund_account.id,
                    "debit_amount": net_excess,
                    "credit_amount": Decimal("0.00"),
                    "description": f"Excess {label} reclassified to member savings",
                },
                {
                    "account_id": savings_account.id,
                    "debit_amount": Decimal("0.00"),
                    "credit_amount": net_excess,
                    "description": f"Savings — excess {label} contribution ({month_label})",
                },
            ],
            created_by=approved_by,
        )
        db.commit()

        result[f"{fund_key}_excess"] = net_excess

    return result


def disburse_loan(
    db: Session,
    loan_id: UUID,
    disbursed_by: UUID,
    bank_cash_account_id: UUID,
    loans_receivable_account_id: UUID,
    disbursement_date_override: date = None,
) -> Loan:
    """Disburse a loan and post to ledger.

    Posts a single balanced journal entry that records BOTH the cash movement
    and the accrued interest revenue:

    - Dr Loans Receivable           (principal)
    - Dr Interest Receivable        (full expected interest)
    - Cr Bank Cash                  (principal disbursed)
    - Cr Interest Income            (full expected interest, recognised NOW)

    The interest is recognised in full at origination — that's the revenue
    that backs this month's share-out, regardless of when the member actually
    pays it. Subsequent interest payments draw down Interest Receivable, not
    Interest Income.

    Falls back to the pre-accrual two-line shape ONLY if INTEREST_RECEIVABLE
    or INTEREST_INCOME ledger accounts are missing (e.g. dev environments
    that haven't run the seed). In that case a warning is logged.
    """
    if isinstance(loan_id, str):
        loan_id = UUID(loan_id)
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise ValueError("Loan not found")

    if loan.loan_status not in [LoanStatus.APPROVED]:
        raise ValueError("Loan must be approved before disbursement")

    disbursement_effective = disbursement_date_override or date.today()

    # Resolve accrual accounts. Both must be present for the new shape.
    interest_receivable = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_RECEIVABLE"
    ).first()
    interest_income = db.query(LedgerAccount).filter(
        LedgerAccount.account_code == "INTEREST_INCOME"
    ).first()

    expected_interest = (
        (loan.loan_amount or Decimal("0.00"))
        * (loan.percentage_interest or Decimal("0.00"))
        / Decimal("100")
    ).quantize(Decimal("0.01"))

    lines = [
        {
            "account_id": loans_receivable_account_id,
            "debit_amount": loan.loan_amount,
            "credit_amount": Decimal("0.00"),
            "description": f"Loan receivable - {loan.member_id}",
        },
        {
            "account_id": bank_cash_account_id,
            "debit_amount": Decimal("0.00"),
            "credit_amount": loan.loan_amount,
            "description": "Bank cash disbursed",
        },
    ]
    if expected_interest > 0 and interest_receivable and interest_income:
        lines.append({
            "account_id": interest_receivable.id,
            "debit_amount": expected_interest,
            "credit_amount": Decimal("0.00"),
            "description": (
                f"Interest receivable — {loan.percentage_interest}% on "
                f"K{loan.loan_amount} ({loan.number_of_instalments or '?'} mo)"
            ),
        })
        lines.append({
            "account_id": interest_income.id,
            "debit_amount": Decimal("0.00"),
            "credit_amount": expected_interest,
            "description": "Interest income recognised at origination",
        })
    elif expected_interest > 0:
        import logging
        logging.getLogger(__name__).warning(
            "disburse_loan: INTEREST_RECEIVABLE or INTEREST_INCOME account missing; "
            "skipping accrual lines on loan %s. Run scripts/setup_ledger_accounts.py "
            "and migration b8c9d0e1f2a3.", loan.id,
        )

    # Create journal entry
    journal_entry = create_journal_entry(
        db=db,
        description=f"Loan disbursement for loan {loan.id}",
        lines=lines,
        dealing_month=get_dealing_month_date(db, loan.cycle_id, disbursement_effective),
        cycle_id=loan.cycle_id,
        source_ref=str(loan.id),
        source_type="loan_disbursement",
        created_by=disbursed_by
    )

    loan.loan_status = LoanStatus.OPEN  # Set to OPEN (active) after disbursement
    loan.disbursement_date = disbursement_effective
    loan.effective_month = loan.disbursement_date
    loan.disbursement_journal_entry_id = journal_entry.id
    # Backdate the actual posting timestamp too so legacy entry_date-based reports stay consistent.
    if disbursement_date_override is not None:
        journal_entry.entry_date = datetime.combine(disbursement_date_override, datetime.min.time())
    
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

    # Look up the loan's cycle so the dealing month uses the cycle's declaration day.
    loan_obj = db.query(Loan).filter(Loan.id == loan_id).first()
    loan_cycle_id = loan_obj.cycle_id if loan_obj else None

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
        dealing_month=get_dealing_month_date(db, loan_cycle_id, repayment_date),
        cycle_id=loan_cycle_id,
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
    """Approve penalty and post to ledger.
    
    When a penalty is approved by the treasurer, it is posted to the ledger
    and the status is changed to APPROVED. The penalty can then be included
    in member declarations and will be marked as PAID when the deposit is approved.
    """
    penalty = db.query(PenaltyRecord).filter(PenaltyRecord.id == penalty_record_id).first()
    if not penalty:
        raise ValueError("Penalty record not found")
    
    # Check if penalty is already approved
    if penalty.status == PenaltyRecordStatus.APPROVED:
        raise ValueError("Penalty has already been approved")
    
    # Check if penalty is already paid
    if penalty.status == PenaltyRecordStatus.PAID:
        raise ValueError("Penalty has already been paid")
    
    # Check if penalty has a penalty_type_id
    if not penalty.penalty_type_id:
        raise ValueError("Penalty record is missing penalty type")
    
    penalty_type = db.query(PenaltyType).filter(PenaltyType.id == penalty.penalty_type_id).first()
    if not penalty_type:
        raise ValueError(f"Penalty type with ID {penalty.penalty_type_id} not found")
    
    # Check if penalty type has a valid fee amount
    if penalty_type.fee_amount is None or penalty_type.fee_amount <= Decimal("0.00"):
        raise ValueError(f"Penalty type '{penalty_type.name}' has invalid fee amount")
    
    # Penalties bucket into the month they were issued, regardless of approval date.
    penalty_effective = penalty.date_issued.date() if penalty.date_issued else date.today()

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
        dealing_month=get_dealing_month_date(db, None, penalty_effective),
        source_ref=str(penalty.id),
        source_type="penalty",
        created_by=approved_by
    )
    
    # Set status to APPROVED (not PAID - that happens when deposit is approved)
    penalty.status = PenaltyRecordStatus.APPROVED.value  # Use .value to ensure lowercase string is sent
    penalty.approved_by = approved_by
    penalty.approved_at = datetime.utcnow()
    penalty.journal_entry_id = journal_entry.id
    
    db.commit()
    db.refresh(penalty)
    return penalty
