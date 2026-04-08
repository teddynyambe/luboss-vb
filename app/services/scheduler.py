"""Background scheduler for automatic loan closure, excess fund transfers,
and activity-window email notifications."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import or_

from app.core.config import settings
from app.db.base import SessionLocal
from app.models.transaction import (
    Declaration, DeclarationStatus, Loan, LoanStatus,
)
from app.models.cycle import Cycle, CycleStatus
from app.models.member import MemberProfile, MemberStatus
from app.models.user import User, UserRoleEnum
from app.services.transaction import post_excess_contributions

logger = logging.getLogger(__name__)

scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Job 1: Close fully-paid loans
# ---------------------------------------------------------------------------

def _close_paid_off_loans(db) -> List[dict]:
    """Find all OPEN loans where principal AND interest are fully paid, then close them.

    Returns a list of dicts describing each closed loan (for the report email).
    """
    open_loans = db.query(Loan).filter(
        Loan.loan_status.in_([LoanStatus.OPEN, LoanStatus.DISBURSED]),
    ).all()

    closed_loans: List[dict] = []
    for loan in open_loans:
        decl_q = db.query(Declaration).filter(
            Declaration.member_id == loan.member_id,
            Declaration.status == DeclarationStatus.APPROVED,
            or_(
                Declaration.declared_loan_repayment > 0,
                Declaration.declared_interest_on_loan > 0,
            ),
        )
        if loan.disbursement_date:
            decl_q = decl_q.filter(
                Declaration.effective_month >= loan.disbursement_date
            )
        paid_decls = decl_q.all()

        total_principal_paid = sum(
            (d.declared_loan_repayment or Decimal("0.00")) for d in paid_decls
        )
        total_interest_paid = sum(
            (d.declared_interest_on_loan or Decimal("0.00")) for d in paid_decls
        )

        outstanding_principal = loan.loan_amount - total_principal_paid
        rate = float(loan.percentage_interest or 0)
        interest_expected = Decimal(str(
            float(loan.loan_amount) * (rate / 100)
        )) if rate > 0 else Decimal("0.00")

        if outstanding_principal <= Decimal("0.01") and total_interest_paid >= interest_expected:
            loan.loan_status = LoanStatus.CLOSED

            # Resolve member name for the report
            member = db.query(MemberProfile).filter(MemberProfile.id == loan.member_id).first()
            member_name = "Unknown"
            if member:
                user = db.query(User).filter(User.id == member.user_id).first()
                if user:
                    member_name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip()

            closed_loans.append({
                "member_name": member_name,
                "loan_amount": float(loan.loan_amount),
            })

    if closed_loans:
        db.commit()
        logger.info("Scheduler auto-closed %d fully-paid loan(s)", len(closed_loans))

    return closed_loans


# ---------------------------------------------------------------------------
# Job 2: Transfer excess admin/social fund contributions to savings
# ---------------------------------------------------------------------------

def _transfer_excess_contributions(db) -> List[dict]:
    """For every active member, transfer any excess social/admin fund to savings.

    Returns a list of dicts describing each transfer (for the report email).
    """
    active_cycle = db.query(Cycle).filter(
        Cycle.status == CycleStatus.ACTIVE,
    ).first()
    if not active_cycle:
        return []

    approved_by = active_cycle.created_by

    active_members = db.query(MemberProfile).filter(
        MemberProfile.status == MemberStatus.ACTIVE,
    ).all()

    transfers: List[dict] = []
    for member in active_members:
        result = post_excess_contributions(
            db=db,
            member_id=member.id,
            cycle=active_cycle,
            effective_month=active_cycle.start_date,
            approved_by=approved_by,
        )
        social_excess = float(result["social_excess"])
        admin_excess = float(result["admin_excess"])

        if social_excess > 0 or admin_excess > 0:
            user = db.query(User).filter(User.id == member.user_id).first()
            member_name = "Unknown"
            if user:
                member_name = f"{(user.first_name or '').strip().title()} {(user.last_name or '').strip().title()}".strip()

            transfers.append({
                "member_name": member_name,
                "social_excess": social_excess,
                "admin_excess": admin_excess,
            })

    if transfers:
        logger.info(
            "Scheduler transferred excess contributions for %d member(s)",
            len(transfers),
        )

    return transfers


# ---------------------------------------------------------------------------
# Orchestrator: runs both jobs, emails treasurers if anything changed
# ---------------------------------------------------------------------------

def run_scheduled_tasks() -> None:
    """Execute both scheduled jobs and notify treasurers when changes occur."""
    db = SessionLocal()
    try:
        closed_loans = _close_paid_off_loans(db)
        excess_transfers = _transfer_excess_contributions(db)

        if not closed_loans and not excess_transfers:
            return

        # Collect all treasurer emails
        treasurers = db.query(User).filter(
            User.role == UserRoleEnum.TREASURER,
        ).all()
        treasurer_emails = [t.email for t in treasurers if t.email]

        if not treasurer_emails:
            return

        from app.core.email import send_scheduler_report
        send_scheduler_report(
            to_emails=treasurer_emails,
            closed_loans=closed_loans,
            excess_transfers=excess_transfers,
        )
    except Exception:
        db.rollback()
        logger.exception("Error in scheduled tasks")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Job 3: Activity-window email notifications
# ---------------------------------------------------------------------------

# Dealing dates each month:
#   Declaration period:             15th – 5th of the next month
#   Loan application period:        21st – 25th
#   Deposit & loan repayment period: 25th – 5th of the next month
#
# On each opening day we email every active member once.

_ACTIVITY_WINDOWS = [
    {
        "trigger_day": 15,
        "name": "Declaration Period",
        "description": (
            "You can now submit your monthly declaration (savings, social fund, "
            "admin fund, penalties, interest, and loan repayment)."
        ),
        "close_day_offset": "next_month_5",
        "path": "/dashboard/member/declarations",
    },
    {
        "trigger_day": 21,
        "name": "Loan Application Period",
        "description": (
            "The loan application window is now open. "
            "Check your eligibility and apply for a loan if needed."
        ),
        "close_day_offset": "same_month_25",
        "path": "/dashboard/member",
    },
    {
        "trigger_day": 25,
        "name": "Deposit & Loan Repayment Period",
        "description": (
            "The deposit and loan repayment window is now open. "
            "Please make your payments and upload proof of deposit."
        ),
        "close_day_offset": "next_month_5",
        "path": "/dashboard/member/deposits",
    },
]


def _closing_date(today: date, offset_type: str) -> date:
    """Calculate the window closing date based on offset type."""
    if offset_type == "next_month_5":
        if today.month == 12:
            return date(today.year + 1, 1, 5)
        return date(today.year, today.month + 1, 5)
    elif offset_type == "same_month_25":
        return date(today.year, today.month, 25)
    return today


def send_activity_window_notifications() -> None:
    """Check if today is a trigger day for any activity window and email all
    active members.  Designed to run once daily (via cron trigger)."""
    today = date.today()
    day = today.day

    windows_to_notify = [w for w in _ACTIVITY_WINDOWS if w["trigger_day"] == day]
    if not windows_to_notify:
        return

    db = SessionLocal()
    try:
        # Fetch all active members with their user (for name + email)
        members_users = (
            db.query(MemberProfile, User)
            .join(User, MemberProfile.user_id == User.id)
            .filter(
                MemberProfile.status == MemberStatus.ACTIVE,
                User.role != UserRoleEnum.ADMIN,
            )
            .all()
        )

        if not members_users:
            return

        from app.core.email import send_activity_window_email
        frontend_url = settings.FRONTEND_URL.rstrip("/")

        for window in windows_to_notify:
            close_date = _closing_date(today, window["close_day_offset"])
            open_str = today.strftime("%d %B %Y")
            close_str = close_date.strftime("%d %B %Y")
            action_url = f"{frontend_url}{window['path']}"

            sent = 0
            for member, user in members_users:
                if not user.email:
                    continue
                first_name = (user.first_name or "Member").strip().title()
                try:
                    send_activity_window_email(
                        to_email=user.email,
                        first_name=first_name,
                        activity_name=window["name"],
                        activity_description=window["description"],
                        window_open_date=open_str,
                        window_close_date=close_str,
                        action_url=action_url,
                    )
                    sent += 1
                except Exception:
                    logger.exception(
                        "Failed to send %s notification to %s",
                        window["name"], user.email,
                    )

            logger.info(
                "Activity window '%s' notifications sent to %d member(s)",
                window["name"], sent,
            )
    except Exception:
        logger.exception("Error in activity window notification job")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler lifecycle helpers
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """Create and start the background scheduler."""
    global scheduler
    interval = settings.SCHEDULER_INTERVAL_MINUTES

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scheduled_tasks,
        trigger=IntervalTrigger(minutes=interval),
        id="run_scheduled_tasks",
        name="Auto-close loans & transfer excess contributions",
        replace_existing=True,
    )
    # Daily job at 07:00 to send activity-window email notifications
    scheduler.add_job(
        send_activity_window_notifications,
        trigger=CronTrigger(hour=7, minute=0),
        id="activity_window_notifications",
        name="Send activity window email notifications to members",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Background scheduler started with interval=%d minutes", interval)


def stop_scheduler() -> None:
    """Shut down the background scheduler gracefully."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
        scheduler = None


def reschedule_jobs(new_interval: int) -> None:
    """Change the interval for all scheduler jobs at runtime."""
    if not scheduler or not scheduler.running:
        raise RuntimeError("Scheduler is not running")

    trigger = IntervalTrigger(minutes=new_interval)
    scheduler.reschedule_job("run_scheduled_tasks", trigger=trigger)
    logger.info("Scheduler jobs rescheduled to interval=%d minutes", new_interval)


def get_scheduler_status() -> dict:
    """Return current scheduler state for the status API."""
    if not scheduler or not scheduler.running:
        return {"running": False, "interval_minutes": None, "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        })

    # Derive current interval from the first job's trigger
    current_interval = settings.SCHEDULER_INTERVAL_MINUTES
    first_job = scheduler.get_jobs()[0] if scheduler.get_jobs() else None
    if first_job and hasattr(first_job.trigger, "interval"):
        current_interval = int(first_job.trigger.interval.total_seconds() / 60)

    return {
        "running": True,
        "interval_minutes": current_interval,
        "jobs": jobs,
    }
