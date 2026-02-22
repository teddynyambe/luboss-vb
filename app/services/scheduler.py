"""Background scheduler for automatic loan closure and excess fund transfers."""

import logging
from decimal import Decimal
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
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
        Loan.loan_status == LoanStatus.OPEN,
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
