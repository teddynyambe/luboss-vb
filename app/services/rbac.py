from sqlalchemy.orm import Session
from app.models.user import User
from app.models.role import Role, UserRole
from datetime import datetime
from typing import List


def get_user_roles(user: User, db: Session) -> List[str]:
    """Get all active role names for a user."""
    now = datetime.utcnow()
    user_roles = db.query(Role.name).join(UserRole).filter(
        UserRole.user_id == user.id,
        (UserRole.start_date.is_(None) | (UserRole.start_date <= now)),
        (UserRole.end_date.is_(None) | (UserRole.end_date >= now)),
        Role.is_active == True
    ).all()
    return [role[0] for role in user_roles]


def assign_role(
    db: Session,
    user_id: str,
    role_name: str,
    assigned_by: str,
    start_date: datetime = None,
    end_date: datetime = None
) -> UserRole:
    """Assign a role to a user."""
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        raise ValueError(f"Role '{role_name}' not found")
    
    user_role = UserRole(
        user_id=user_id,
        role_id=role.id,
        assigned_by=assigned_by,
        start_date=start_date,
        end_date=end_date
    )
    db.add(user_role)
    db.commit()
    db.refresh(user_role)
    return user_role
