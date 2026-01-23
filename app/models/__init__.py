from app.db.base import Base

# Import all models so Alembic can detect them
from app.models.user import User
from app.models.member import MemberProfile, MemberStatusHistory
from app.models.role import Role, UserRole
from app.models.ledger import (
    LedgerAccount,
    JournalEntry,
    JournalLine,
    PostingLock,
)
from app.models.cycle import Cycle, CyclePhase
from app.models.transaction import (
    Declaration,
    DepositProof,
    DepositApproval,
    LoanApplication,
    Loan,
    Repayment,
    PenaltyType,
    PenaltyRecord,
)
from app.models.policy import (
    CreditRatingScheme,
    CreditRatingTier,
    MemberCreditRating,
    InterestPolicy,
    InterestThresholdPolicy,
    BorrowingLimitPolicy,
    CreditRatingInterestRange,
    PolicyVersion,
    CollateralPolicyVersion,
    CollateralAsset,
    CollateralValuation,
    CollateralHold,
)
from app.models.system import SystemSettings, VBGroup, CommitteeAssignment, ConstitutionDocumentVersion
from app.models.ai import DocumentChunk, DocumentEmbedding, AIAuditLog
from app.models.migration import (
    IdMapUser,
    IdMapMember,
    IdMapLoan,
    StgMembers,
    StgDeposits,
    StgLoans,
    StgRepayments,
    StgPenalties,
    StgCycles,
)

__all__ = [
    "Base",
    "User",
    "MemberProfile",
    "MemberStatusHistory",
    "Role",
    "UserRole",
    "LedgerAccount",
    "JournalEntry",
    "JournalLine",
    "PostingLock",
    "Cycle",
    "CyclePhase",
    "Declaration",
    "DepositProof",
    "DepositApproval",
    "LoanApplication",
    "Loan",
    "Repayment",
    "PenaltyType",
    "PenaltyRecord",
    "CreditRatingScheme",
    "CreditRatingTier",
    "MemberCreditRating",
    "InterestPolicy",
    "InterestThresholdPolicy",
    "BorrowingLimitPolicy",
    "CreditRatingInterestRange",
    "PolicyVersion",
    "CollateralPolicyVersion",
    "CollateralAsset",
    "CollateralValuation",
    "CollateralHold",
    "SystemSettings",
    "VBGroup",
    "CommitteeAssignment",
    "ConstitutionDocumentVersion",
    "DocumentChunk",
    "DocumentEmbedding",
    "AIAuditLog",
    "IdMapUser",
    "IdMapMember",
    "IdMapLoan",
    "StgMembers",
    "StgDeposits",
    "StgLoans",
    "StgRepayments",
    "StgPenalties",
    "StgCycles",
]
