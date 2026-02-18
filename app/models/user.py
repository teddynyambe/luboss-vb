from sqlalchemy import Column, String, Boolean, Text, DateTime, Enum as SQLEnum, Uuid, text
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base
import enum


class UserRoleEnum(str, enum.Enum):
    """Legacy user role enum - preserved from old system."""
    ADMIN = "admin"
    TREASURER = "treasurer"
    MEMBER = "member"
    COMPLIANCE = "compliance"
    CHAIRMAN = "chairman"


class User(Base):
    """Legacy user table - preserved exactly as-is for authentication."""
    __tablename__ = "user"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone_number = Column(String(20), nullable=True)
    bank_account = Column(String(50), nullable=True)
    bank_name = Column(String(100), nullable=True)
    bank_branch = Column(String(100), nullable=True)
    nrc_number = Column(String(50), nullable=True, unique=True, index=True)
    physical_address = Column(Text, nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRoleEnum, native_enum=False, values_callable=lambda obj: [e.value for e in obj]), default=UserRoleEnum.MEMBER)
    approved = Column(Boolean, nullable=True, default=None)
    first_name_next_of_kin = Column(String(100), nullable=True)
    last_name_next_of_kin = Column(String(100), nullable=True)
    phone_number_next_of_kin = Column(String(20), nullable=True)
    date_joined = Column(DateTime, nullable=True, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    member_profile = relationship("MemberProfile", back_populates="user", uselist=False, foreign_keys="[MemberProfile.user_id]")
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="[UserRole.user_id]")
