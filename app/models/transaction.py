from sqlalchemy import Column, String, ForeignKey, DateTime, Date, Numeric, Enum as SQLEnum, Text, TypeDecorator, Uuid, text, func
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
import enum
from decimal import Decimal


class DeclarationStatus(str, enum.Enum):
    """Declaration status."""
    PENDING = "pending"
    PROOF = "proof"
    APPROVED = "approved"
    REJECTED = "rejected"


class LoanApplicationStatus(str, enum.Enum):
    """Loan application status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class LoanStatus(str, enum.Enum):
    """Loan status."""
    PENDING = "pending"
    APPROVED = "approved"
    DISBURSED = "disbursed"
    CLOSED = "closed"
    OPEN = "open"
    WITHDRAWN = "withdrawn"
    REJECTED = "rejected"


class PenaltyRecordStatus(str, enum.Enum):
    """Penalty record status."""
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"


class PenaltyRecordStatusType(TypeDecorator):
    """Custom type to ensure enum values (lowercase strings) are used instead of enum names.

    The database enum expects lowercase values ('approved', 'pending', 'paid'),
    but SQLAlchemy's SQLEnum uses enum names by default. This TypeDecorator
    uses String as the base type and handles conversion to ensure lowercase values.
    """
    # Use String as the base type - we'll cast it to the enum in SQL
    impl = String(20)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        """Return the dialect-specific implementation."""
        return dialect.type_descriptor(String(20))

    def process_bind_param(self, value, dialect):
        """Convert enum to its value (lowercase string) when binding to database."""
        if value is None:
            return None

        # If it's an enum instance, get its value
        if isinstance(value, PenaltyRecordStatus):
            return value.value  # Return "approved", "pending", or "paid"

        # If it's already a string, check if it's an enum name (uppercase) or value (lowercase)
        if isinstance(value, str):
            # Map enum names to values
            name_to_value = {
                'PENDING': 'pending',
                'APPROVED': 'approved',
                'PAID': 'paid'
            }
            # If it's an uppercase enum name, convert to lowercase value
            if value in name_to_value:
                return name_to_value[value]
            # Otherwise, ensure it's lowercase
            return value.lower()

        return value

    def process_result_value(self, value, dialect):
        """Convert database value back to enum when reading."""
        if value is None:
            return None
        if isinstance(value, str):
            # Convert string to enum
            try:
                return PenaltyRecordStatus(value.lower())
            except ValueError:
                return value
        return value


class DepositProofStatus(str, enum.Enum):
    """Deposit proof status."""
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class Declaration(Base):
    """Member declaration of intent (savings, contributions, repayment plan)."""
    __tablename__ = "declaration"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    effective_month = Column(Date, nullable=False)
    declared_savings_amount = Column(Numeric(10, 2), nullable=True)
    declared_social_fund = Column(Numeric(10, 2), nullable=True)
    declared_admin_fund = Column(Numeric(10, 2), nullable=True)
    declared_penalties = Column(Numeric(10, 2), nullable=True)
    declared_interest_on_loan = Column(Numeric(10, 2), nullable=True)
    declared_loan_repayment = Column(Numeric(10, 2), nullable=True)
    status = Column(SQLEnum(DeclarationStatus, native_enum=False, values_callable=lambda obj: [e.value for e in obj]), default=DeclarationStatus.PENDING, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    member = relationship("MemberProfile", back_populates="declarations")
    cycle = relationship("Cycle", back_populates="declarations")
    deposit_proofs = relationship("DepositProof", back_populates="declaration")


class DepositProof(Base):
    """Member upload of proof of payment."""
    __tablename__ = "deposit_proof"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    declaration_id = Column(Uuid(as_uuid=True), ForeignKey("declaration.id"), nullable=True, index=True)
    upload_path = Column(String(500), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    reference = Column(String(100), nullable=True)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=True, index=True)
    status = Column(String(20), default=DepositProofStatus.SUBMITTED.value, nullable=False)
    treasurer_comment = Column(Text, nullable=True)
    member_response = Column(Text, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejected_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    uploaded_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    member = relationship("MemberProfile", back_populates="deposit_proofs")
    declaration = relationship("Declaration", back_populates="deposit_proofs")
    approval = relationship("DepositApproval", back_populates="deposit_proof", uselist=False)


class DepositApproval(Base):
    """Treasurer approval of deposit proof and journal linkage."""
    __tablename__ = "deposit_approval"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deposit_proof_id = Column(Uuid(as_uuid=True), ForeignKey("deposit_proof.id"), nullable=False, unique=True, index=True)
    journal_entry_id = Column(Uuid(as_uuid=True), ForeignKey("journal_entry.id"), nullable=False, unique=True, index=True)
    approved_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False)
    approved_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    notes = Column(Text, nullable=True)

    # Relationships
    deposit_proof = relationship("DepositProof", back_populates="approval")
    journal_entry = relationship("JournalEntry", backref="deposit_approval")


class LoanApplication(Base):
    """Loan application."""
    __tablename__ = "loan_application"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    term_months = Column(String(10), nullable=False)  # e.g., "1", "2", "3", "4"
    notes = Column(Text, nullable=True)  # Member's notes/remarks on the loan application
    status = Column(SQLEnum(LoanApplicationStatus, native_enum=False, values_callable=lambda obj: [e.value for e in obj]), default=LoanApplicationStatus.PENDING, nullable=False)
    application_date = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    reviewed_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Relationships
    member = relationship("MemberProfile", back_populates="loan_applications")
    cycle = relationship("Cycle", back_populates="loan_applications")
    loan = relationship("Loan", back_populates="application", uselist=False)


class Loan(Base):
    """Approved loan."""
    __tablename__ = "loan"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(Uuid(as_uuid=True), ForeignKey("loan_application.id"), nullable=True, unique=True, index=True)
    member_id = Column(Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    loan_amount = Column(Numeric(10, 2), nullable=False)
    percentage_interest = Column(Numeric(5, 2), nullable=False)
    effective_month = Column(Date, nullable=True)
    repayment_start_date = Column(Date, nullable=True)
    repayment_end_date = Column(Date, nullable=True)
    number_of_instalments = Column(String(10), nullable=True)
    loan_status = Column(SQLEnum(LoanStatus, native_enum=False, values_callable=lambda obj: [e.value for e in obj]), default=LoanStatus.PENDING, nullable=False)
    disbursement_date = Column(Date, nullable=True)
    disbursement_journal_entry_id = Column(Uuid(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    application = relationship("LoanApplication", back_populates="loan")
    member = relationship("MemberProfile", back_populates="loans")
    cycle = relationship("Cycle", back_populates="loans")
    repayments = relationship("Repayment", back_populates="loan")
    collateral_holds = relationship("CollateralHold", back_populates="loan")


class Repayment(Base):
    """Loan repayment (splits principal and interest)."""
    __tablename__ = "repayment"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id = Column(Uuid(as_uuid=True), ForeignKey("loan.id"), nullable=False, index=True)
    repayment_date = Column(Date, nullable=False)
    principal_amount = Column(Numeric(10, 2), nullable=False)
    interest_amount = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    journal_entry_id = Column(Uuid(as_uuid=True), ForeignKey("journal_entry.id"), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    loan = relationship("Loan", back_populates="repayments")
    journal_entry = relationship("JournalEntry", backref="repayment")


class PenaltyType(Base):
    """Penalty type definition."""
    __tablename__ = "penalty_type"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    fee_amount = Column(Numeric(10, 2), nullable=False)
    enabled = Column(String(10), nullable=False, default="1")  # "1" or "0" to match old system
    date_added = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    penalty_records = relationship("PenaltyRecord", back_populates="penalty_type")


class PenaltyRecord(Base):
    """Penalty record (created by compliance, approved by treasurer)."""
    __tablename__ = "penalty_record"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(Uuid(as_uuid=True), ForeignKey("member_profile.id"), nullable=False, index=True)
    penalty_type_id = Column(Uuid(as_uuid=True), ForeignKey("penalty_type.id"), nullable=False, index=True)
    date_issued = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    status = Column(PenaltyRecordStatusType(), default=PenaltyRecordStatus.PENDING.value, nullable=False)
    created_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False)
    approved_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    journal_entry_id = Column(Uuid(as_uuid=True), ForeignKey("journal_entry.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    # Relationships
    member = relationship("MemberProfile", back_populates="penalty_records")
    penalty_type = relationship("PenaltyType", back_populates="penalty_records")
    journal_entry = relationship("JournalEntry", backref="penalty_record")


class BankStatement(Base):
    """Treasurer-uploaded bank statement for a cycle month."""
    __tablename__ = "bank_statement"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(Uuid(as_uuid=True), ForeignKey("cycle.id"), nullable=False, index=True)
    statement_month = Column(Date, nullable=False)       # stored as YYYY-MM-01
    description = Column(Text, nullable=True)            # narration / notes
    upload_path = Column(String(500), nullable=False)
    uploaded_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    cycle = relationship("Cycle", backref="bank_statements")
