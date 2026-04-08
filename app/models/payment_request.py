"""Payment request model for expense workflows."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Column, DateTime, Enum as SQLEnum, ForeignKey, Index, Numeric, String, Text, Uuid, text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class PaymentRequestStatus(str, enum.Enum):
    PENDING = "pending"        # Vice-Chair created, awaiting Chairman approval
    APPROVED = "approved"      # Chairman approved, awaiting Treasurer execution
    REJECTED = "rejected"      # Chairman rejected
    EXECUTED = "executed"      # Treasurer executed, journal entry posted
    CANCELLED = "cancelled"    # Initiator cancelled before approval


class PaymentCategory(str, enum.Enum):
    COMMITTEE_PAYMENT = "committee_payment"    # Admin Fund source
    SOCIAL_SUPPORT = "social_support"          # Social Fund source
    ADMIN_COST = "admin_cost"                  # Admin Fund source
    END_OF_YEAR_PAYOUT = "end_of_year_payout"  # Bank Cash → member savings


# Category → default source account code mapping
CATEGORY_SOURCE_MAP = {
    PaymentCategory.COMMITTEE_PAYMENT: "ADMIN_FUND",
    PaymentCategory.SOCIAL_SUPPORT: "SOCIAL_FUND",
    PaymentCategory.ADMIN_COST: "ADMIN_FUND",
    PaymentCategory.END_OF_YEAR_PAYOUT: "BANK_CASH",
}


class PaymentRequest(Base):
    """Payment / expense request with 3-step approval workflow."""

    __tablename__ = "payment_request"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── What ─────────────────────────────────────────────────────────────────
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(
        SQLEnum(PaymentCategory, native_enum=False,
                values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    source_account_code = Column(String(20), nullable=False)

    # ── Who receives ─────────────────────────────────────────────────────────
    beneficiary_name = Column(String(200), nullable=False)
    beneficiary_member_id = Column(
        Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=True,
    )

    # ── Cycle ────────────────────────────────────────────────────────────────
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=True)

    # ── Workflow status ──────────────────────────────────────────────────────
    status = Column(
        SQLEnum(PaymentRequestStatus, native_enum=False,
                values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=PaymentRequestStatus.PENDING,
    )

    # ── Step 1: Initiation (Vice-Chairman or Chairman) ───────────────────────
    initiated_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False)
    initiated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # ── Step 2: Approval (Chairman) ──────────────────────────────────────────
    approved_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # ── Step 3: Execution (Treasurer) ────────────────────────────────────────
    executed_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    journal_entry_id = Column(Uuid(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True)
    payment_reference = Column(String(100), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    initiator = relationship("User", foreign_keys=[initiated_by])
    approver = relationship("User", foreign_keys=[approved_by])
    executor = relationship("User", foreign_keys=[executed_by])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
    beneficiary_member = relationship("MemberProfile", foreign_keys=[beneficiary_member_id])
    cycle = relationship("Cycle", foreign_keys=[cycle_id])

    __table_args__ = (
        Index("idx_payment_request_status", "status"),
        Index("idx_payment_request_initiated_by", "initiated_by"),
        Index("idx_payment_request_cycle_id", "cycle_id"),
    )
