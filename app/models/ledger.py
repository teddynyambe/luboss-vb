from sqlalchemy import Column, String, ForeignKey, DateTime, Numeric, Enum as SQLEnum, Boolean, Text, Index, Uuid, text
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
import enum
from decimal import Decimal


class AccountType(str, enum.Enum):
    """Ledger account type."""
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"
    EQUITY = "equity"


class LedgerAccount(Base):
    """Chart of accounts."""
    __tablename__ = "ledger_account"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_code = Column(String(20), nullable=False, unique=True, index=True)
    account_name = Column(String(100), nullable=False)
    account_type = Column(SQLEnum(AccountType, native_enum=False, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    parent_account_id = Column(Uuid(as_uuid=True), ForeignKey("ledger_account.id"), nullable=True)
    member_id = Column(Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=True, index=True)  # For sub-ledgers
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    parent_account = relationship("LedgerAccount", remote_side=[id], backref="sub_accounts")
    journal_lines = relationship("JournalLine", back_populates="account")


class JournalEntry(Base):
    """Journal entry header (transaction)."""
    __tablename__ = "journal_entry"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_date = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
    description = Column(String(255), nullable=False)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=True, index=True)
    source_ref = Column(String(100), nullable=True)  # For migration traceability (e.g., "old_transaction_id")
    source_type = Column(String(50), nullable=True)  # e.g., "deposit", "loan_disbursement", "repayment"
    created_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    reversed_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    reversed_at = Column(DateTime, nullable=True)
    reversal_reason = Column(Text, nullable=True)

    # Relationships
    journal_lines = relationship("JournalLine", back_populates="journal_entry", cascade="all, delete-orphan")


class JournalLine(Base):
    """Journal line (debit or credit)."""
    __tablename__ = "journal_line"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_entry_id = Column(Uuid(as_uuid=True), ForeignKey("journal_entry.id"), nullable=False, index=True)
    ledger_account_id = Column(Uuid(as_uuid=True), ForeignKey("ledger_account.id"), nullable=False, index=True)
    debit_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    credit_amount = Column(Numeric(15, 2), nullable=False, default=Decimal("0.00"))
    description = Column(String(255), nullable=True)

    # Relationships
    journal_entry = relationship("JournalEntry", back_populates="journal_lines")
    account = relationship("LedgerAccount", back_populates="journal_lines")

    # Index for balance queries
    __table_args__ = (
        Index("idx_journal_line_account_date", "ledger_account_id", "journal_entry_id"),
    )


class PostingLock(Base):
    """Cycle-level posting locks to prevent edits."""
    __tablename__ = "posting_lock"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=False, unique=True, index=True)
    locked_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    locked_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False)
    reason = Column(Text, nullable=True)
