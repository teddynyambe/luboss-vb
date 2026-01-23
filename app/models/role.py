from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class Role(Base):
    """RBAC role definitions."""
    __tablename__ = "role"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default="now()")
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    user_roles = relationship("UserRole", back_populates="role")


class UserRole(Base):
    """Many-to-many relationship between users and roles with effective dates."""
    __tablename__ = "user_role"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("role.id"), nullable=False, index=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("user.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=False, server_default="now()")
    
    # Relationships
    user = relationship("User", back_populates="user_roles", foreign_keys=[user_id])
    role = relationship("Role", back_populates="user_roles")
