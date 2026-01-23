from datetime import timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.models.member import MemberProfile, MemberStatus
from app.services.member import get_member_profile_by_user_id
from fastapi import HTTPException, status


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate user by email and password. Check if member is not suspended."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    
    # Check if user is a member and if member profile is suspended
    member_profile = get_member_profile_by_user_id(db, user.id)
    if member_profile and member_profile.status == MemberStatus.SUSPENDED:
        return None  # Suspended members cannot login
    
    return user


def create_user(
    db: Session,
    email: str,
    password: str,
    first_name: str = None,
    last_name: str = None,
    **kwargs
) -> User:
    """Create a new user and member profile (PENDING status)."""
    from sqlalchemy.exc import IntegrityError
    
    # Check if user already exists by email
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if NRC number already exists (if provided)
    nrc_number = kwargs.get('nrc_number')
    if nrc_number:
        existing_nrc = db.query(User).filter(User.nrc_number == nrc_number).first()
        if existing_nrc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="NRC number already registered"
            )
    
    # Create user
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        **kwargs
    )
    db.add(user)
    
    try:
        db.flush()  # Get user.id
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig)
        if 'nrc_number' in error_msg.lower() or 'ix_user_nrc_number' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="NRC number already registered"
            )
        elif 'email' in error_msg.lower() or 'ix_user_email' in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed. Please check your information and try again."
            )
    
    # Create member profile with PENDING status
    try:
        member_profile = MemberProfile(
            user_id=user.id,
            status=MemberStatus.PENDING
        )
        db.add(member_profile)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create member profile. Please try again."
        )


def create_access_token_for_user(user: User) -> str:
    """Create access token for user."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
