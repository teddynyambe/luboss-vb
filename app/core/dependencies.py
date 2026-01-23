from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.models.user import User, UserRoleEnum
from app.models.role import Role, UserRole
from app.core.security import decode_access_token
from datetime import datetime
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception
    
    # Convert string UUID to UUID object
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user (approved)."""
    if current_user.approved is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not approved"
        )
    return current_user


def has_role(user: User, role_name: str, db: Session) -> bool:
    """Check if user has a specific role (active assignment).
    
    Checks both RBAC system (role/user_role tables) and legacy enum (user.role).
    Maps legacy enum values to RBAC role names:
    - admin -> Admin
    - chairman -> Chairman
    - treasurer -> Treasurer
    - compliance -> Compliance
    - member -> Member
    """
    # First check RBAC system
    now = datetime.utcnow()
    user_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.name == role_name,
        (UserRole.start_date.is_(None) | (UserRole.start_date <= now)),
        (UserRole.end_date.is_(None) | (UserRole.end_date >= now))
    ).first()
    if user_role is not None:
        return True
    
    # Fallback to legacy enum role
    if user.role:
        # Map legacy enum to RBAC role names
        legacy_to_rbac = {
            UserRoleEnum.ADMIN: "Admin",
            UserRoleEnum.CHAIRMAN: "Chairman",
            UserRoleEnum.TREASURER: "Treasurer",
            UserRoleEnum.COMPLIANCE: "Compliance",
            UserRoleEnum.MEMBER: "Member"
        }
        legacy_role_name = legacy_to_rbac.get(user.role)
        if legacy_role_name == role_name:
            return True
    
    return False


def require_role(role_name: str):
    """Dependency factory for requiring a specific role."""
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        if not has_role(current_user, role_name, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have required role: {role_name}"
            )
        return current_user
    return role_checker


# Role-specific dependencies
require_admin = require_role("Admin")
require_chairman = require_role("Chairman")
require_vice_chairman = require_role("Vice-Chairman")
require_treasurer = require_role("Treasurer")
require_compliance = require_role("Compliance")
require_member = require_role("Member")


def require_any_role(*role_names: str):
    """Dependency factory for requiring any of the specified roles."""
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        for role_name in role_names:
            if has_role(current_user, role_name, db):
                return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have any of the required roles: {', '.join(role_names)}"
        )
    return role_checker


def require_not_admin():
    """Dependency that allows all authenticated users except admin."""
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ) -> User:
        if has_role(current_user, "Admin", db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin users cannot apply for loans"
            )
        return current_user
    return role_checker
