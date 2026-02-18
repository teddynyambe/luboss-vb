from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Uuid, text, func
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class SystemSettings(Base):
    """System settings (SMTP, AI config, feature flags)."""
    __tablename__ = "system_settings"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    setting_key = Column(String(100), nullable=False, unique=True, index=True)
    setting_value = Column(Text, nullable=True)  # Encrypted for sensitive values
    setting_type = Column(String(50), nullable=False)  # "smtp", "ai", "feature_flag", etc.
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())
    updated_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)


class VBGroup(Base):
    """Village Banking group (single group for now, extensible)."""
    __tablename__ = "vb_group"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


class CommitteeAssignment(Base):
    """Committee role assignment with effective dates."""
    __tablename__ = "committee_assignment"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)
    role_id = Column(Uuid(as_uuid=True), ForeignKey("role.id"), nullable=False, index=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    assigned_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    notes = Column(Text, nullable=True)


class ConstitutionDocumentVersion(Base):
    """Versioned constitution document."""
    __tablename__ = "constitution_document_version"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_number = Column(String(20), nullable=False)
    document_path = Column(String(500), nullable=False)  # Path to PDF file
    uploaded_by = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    effective_from = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(String(10), nullable=False, default="1")  # "1" or "0"
