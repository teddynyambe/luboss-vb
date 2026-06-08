"""Interest revenue report — month rollup + per-loan drill-down.

Built for the Treasurer dashboard. Mirrors the accrual-at-origination policy:
the **full** expected interest on a loan is recognised as income in the
disbursement month, regardless of when (or whether) the member ever pays it.
That accrual is what backs the month's profit pool.

Each loan's life cycle in this report:
  * **Accrued** = (loan_amount × percentage_interest / 100), credited at
    disbursement. Bucketed under the loan's disbursement month.
  * **Collected** = sum of live Repayment.interest_amount up to a given
    point. Bucketed under the repayment_date's month.
  * **Outstanding receivable** = accrued − collected. Aging is measured in
    days since the loan's disbursement_date.

Reversed JEs are excluded from collected. Loans without a disbursement_date
are skipped (they were never properly disbursed).
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cycle import Cycle
from app.models.ledger import JournalEntry
from app.models.transaction import Loan, Repayment


def _yyyymm(d: _date) -> str:
    return d.strftime("%Y-%m")


def _month_label(d: _date) -> str:
    return d.strftime("%B %Y")


def _expected_interest(loan: Loan) -> Decimal:
    return (
        (loan.loan_amount or Decimal("0.00"))
        * (loan.percentage_interest or Decimal("0.00"))
        / Decimal("100")
    ).quantize(Decimal("0.01"))


def _days_since(d: _date, today: _date) -> int:
    return max(0, (today - d).days)


def _aging_bucket(days: int) -> str:
    if days <= 30:
        return "current"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "over_90"


def get_interest_revenue_report(
    db: Session,
    cycle_id: Optional[str] = None,
) -> dict:
    """Return the full interest-revenue report payload.

    Shape:
        {
            "cycle_id": str | null,
            "cycle_label": str | null,
            "today": "YYYY-MM-DD",
            "months": [
                {
                    "month": "YYYY-MM-DD",       # 1st of month
                    "month_label": "February 2026",
                    "loans_disbursed_count": int,
                    "loans_disbursed_amount": float,
                    "interest_accrued": float,
                    "interest_collected": float,
                    "outstanding_from_this_month": float,
                    "collection_pct": float | null,    # collected / accrued, null if no accrual
                    "loans": [
                        {
                            "loan_id": str,
                            "member_id": str,
                            "member_name": str,
                            "loan_amount": float,
                            "term_months": str | null,
                            "rate_pct": float,
                            "interest_accrued": float,
                            "interest_collected": float,    # against THIS loan all-time
                            "outstanding": float,
                            "loan_status": str,
                            "aging_days": int,
                            "aging_bucket": "current" | "31_60" | "61_90" | "over_90",
                        }, ...
                    ],
                }, ...
            ],
            "totals": {
                "loans_disbursed_count": int,
                "loans_disbursed_amount": float,
                "interest_accrued": float,
                "interest_collected": float,
                "outstanding": float,
                "collection_pct": float | null,
            },
            "top_outstanding_borrowers": [   # top 5 by outstanding receivable
                {"member_id": str, "member_name": str, "outstanding": float},
                ...
            ],
        }
    """
    from app.models.user import User
    from app.models.member import MemberProfile

    today = _date.today()

    cycle = None
    if cycle_id:
        cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()

    from app.services.loan_repair import loan_has_live_disbursement
    loan_q = db.query(Loan).filter(Loan.disbursement_date.isnot(None))
    if cycle:
        loan_q = loan_q.filter(Loan.cycle_id == cycle.id)
    all_loans = loan_q.order_by(Loan.disbursement_date.asc()).all()
    # Filter out loans whose disbursement JE has been reversed — those don't
    # represent real money on the books and would inflate every metric.
    loans = [L for L in all_loans if loan_has_live_disbursement(db, L.id)]

    if not loans:
        return {
            "cycle_id": str(cycle.id) if cycle else None,
            "cycle_label": cycle.year if cycle else None,
            "today": today.isoformat(),
            "months": [],
            "totals": {
                "loans_disbursed_count": 0,
                "loans_disbursed_amount": 0.0,
                "interest_accrued": 0.0,
                "interest_collected": 0.0,
                "outstanding": 0.0,
                "collection_pct": None,
            },
            "top_outstanding_borrowers": [],
        }

    # Member name lookup — single batched query.
    member_ids = list({L.member_id for L in loans})
    profiles = (
        db.query(MemberProfile, User)
        .join(User, User.id == MemberProfile.user_id)
        .filter(MemberProfile.id.in_(member_ids))
        .all()
    )
    name_by_member: dict[str, str] = {}
    for prof, user in profiles:
        name_by_member[str(prof.id)] = (
            f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
            or "(unknown)"
        )

    # Live repayments for these loans — single query.
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

    # Per-loan totals
    interest_paid_by_loan: dict[str, Decimal] = {}
    for rep, _je in rep_rows:
        interest_paid_by_loan[str(rep.loan_id)] = (
            interest_paid_by_loan.get(str(rep.loan_id), Decimal("0.00"))
            + (rep.interest_amount or Decimal("0.00"))
        )

    # Build per-month buckets keyed by YYYY-MM string.
    months: dict[str, dict] = {}

    def _ensure_month(d: _date) -> dict:
        key = _yyyymm(d)
        if key not in months:
            months[key] = {
                "month": _date(d.year, d.month, 1).isoformat(),
                "month_label": _month_label(d),
                "loans_disbursed_count": 0,
                "loans_disbursed_amount": Decimal("0.00"),
                "interest_accrued": Decimal("0.00"),
                "interest_collected": Decimal("0.00"),
                "loans": [],
            }
        return months[key]

    # Disbursement bucketing
    for L in loans:
        bucket = _ensure_month(L.disbursement_date)
        accrued = _expected_interest(L)
        bucket["loans_disbursed_count"] += 1
        bucket["loans_disbursed_amount"] += L.loan_amount or Decimal("0.00")
        bucket["interest_accrued"] += accrued
        collected_this_loan = interest_paid_by_loan.get(str(L.id), Decimal("0.00"))
        aging_days = _days_since(L.disbursement_date, today)
        bucket["loans"].append({
            "loan_id": str(L.id),
            "member_id": str(L.member_id),
            "member_name": name_by_member.get(str(L.member_id), "(unknown)"),
            "loan_amount": float(L.loan_amount or 0),
            "term_months": L.number_of_instalments,
            "rate_pct": float(L.percentage_interest or 0),
            "interest_accrued": float(accrued),
            "interest_collected": float(collected_this_loan.quantize(Decimal("0.01"))),
            "outstanding": float(max(Decimal("0.00"), accrued - collected_this_loan).quantize(Decimal("0.01"))),
            "loan_status": L.loan_status.value if L.loan_status else None,
            "aging_days": aging_days,
            "aging_bucket": _aging_bucket(aging_days),
        })

    # Collection bucketing — by Repayment.repayment_date month
    for rep, _je in rep_rows:
        if rep.repayment_date is None:
            continue
        bucket = _ensure_month(rep.repayment_date)
        bucket["interest_collected"] += rep.interest_amount or Decimal("0.00")

    # Materialise + sort (most recent first)
    months_list = sorted(months.values(), key=lambda m: m["month"], reverse=True)
    for m in months_list:
        accrued = m["interest_accrued"]
        collected = m["interest_collected"]
        # "outstanding_from_this_month" = how much of *this month's* accrual is
        # still unpaid. Drill-down loans carry their own collected totals
        # (which can include payments made in later months — that's correct
        # for the per-loan outstanding view).
        outstanding_from_this_month = sum(
            (Decimal(str(l["outstanding"])) for l in m["loans"]),
            Decimal("0.00"),
        )
        m["loans_disbursed_amount"] = float(m["loans_disbursed_amount"])
        m["interest_accrued"] = float(accrued.quantize(Decimal("0.01")))
        m["interest_collected"] = float(collected.quantize(Decimal("0.01")))
        m["outstanding_from_this_month"] = float(outstanding_from_this_month.quantize(Decimal("0.01")))
        m["collection_pct"] = (
            float((collected / accrued * Decimal("100")).quantize(Decimal("0.1")))
            if accrued > 0
            else None
        )
        # Sort drill-down rows by outstanding desc so problem loans surface.
        m["loans"].sort(key=lambda r: r["outstanding"], reverse=True)

    # Grand totals
    total_count = sum(m["loans_disbursed_count"] for m in months_list)
    total_disbursed = sum(m["loans_disbursed_amount"] for m in months_list)
    total_accrued = sum(m["interest_accrued"] for m in months_list)
    total_collected = sum(m["interest_collected"] for m in months_list)
    total_outstanding = sum(m["outstanding_from_this_month"] for m in months_list)

    # Top 5 borrowers by outstanding receivable across all months
    outstanding_by_member: dict[str, Decimal] = {}
    for L in loans:
        accrued = _expected_interest(L)
        collected = interest_paid_by_loan.get(str(L.id), Decimal("0.00"))
        outstanding = max(Decimal("0.00"), accrued - collected)
        outstanding_by_member[str(L.member_id)] = (
            outstanding_by_member.get(str(L.member_id), Decimal("0.00")) + outstanding
        )
    top_borrowers = sorted(
        (
            {
                "member_id": mid,
                "member_name": name_by_member.get(mid, "(unknown)"),
                "outstanding": float(amt.quantize(Decimal("0.01"))),
            }
            for mid, amt in outstanding_by_member.items()
            if amt > 0
        ),
        key=lambda r: r["outstanding"],
        reverse=True,
    )[:5]

    return {
        "cycle_id": str(cycle.id) if cycle else None,
        "cycle_label": cycle.year if cycle else None,
        "today": today.isoformat(),
        "months": months_list,
        "totals": {
            "loans_disbursed_count": total_count,
            "loans_disbursed_amount": float(total_disbursed),
            "interest_accrued": float(total_accrued),
            "interest_collected": float(total_collected),
            "outstanding": float(total_outstanding),
            "collection_pct": (
                round(total_collected / total_accrued * 100, 1)
                if total_accrued > 0
                else None
            ),
        },
        "top_outstanding_borrowers": top_borrowers,
    }
