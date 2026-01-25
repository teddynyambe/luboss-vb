from datetime import timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.models.member import MemberProfile, MemberStatus
from app.services.member import get_member_profile_by_user_id
from fastapi import HTTPException, status


def authenticate_user(db: Session, email: str, password: str, migrate_password: bool = True) -> Optional[User]:
    """
    Authenticate user by email and password. Check if member is not suspended.
    
    Args:
        db: Database session
        email: User email
        password: Plain text password
        migrate_password: If True, migrate scrypt passwords to bcrypt on successful login
    
    Returns:
        User object if authentication succeeds, None otherwise
    """
    import logging
    logger = logging.getLogger(__name__)
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.debug(f"User not found: {email}")
        return None
    
    # Check if password is correct
    logger.debug(f"Verifying password for user: {email}, hash format: {'scrypt' if user.password_hash.startswith('scrypt:') else 'bcrypt'}")
    if not verify_password(password, user.password_hash):
        logger.debug(f"Password verification failed for user: {email}")
        return None
    
    logger.debug(f"Password verified successfully for user: {email}")
    
    # Migrate scrypt password to bcrypt if needed (optional gradual migration)
    if migrate_password and user.password_hash.startswith('scrypt:'):
        try:
            logger.info(f"Migrating scrypt password to bcrypt for user: {email}")
            user.password_hash = get_password_hash(password)
            db.commit()
            db.refresh(user)  # Refresh to get updated hash
            logger.info(f"Password migration successful for user: {email}")
        except Exception as e:
            # If migration fails, don't fail authentication - just log it
            db.rollback()
            logger.warning(f"Failed to migrate password hash for user {email}: {e}", exc_info=True)
    
    # Check if user is a member and if member profile is inactive
    member_profile = get_member_profile_by_user_id(db, user.id)
    if member_profile and member_profile.status == MemberStatus.INACTIVE:
        logger.debug(f"User {email} has inactive member profile, login denied")
        return None  # Inactive members cannot login
    
    logger.debug(f"Authentication successful for user: {email}")
    return user


def create_user(
    db: Session,
    email: str,
    password: str,
    first_name: str = None,
    last_name: str = None,
    **kwargs
) -> User:
    """Create a new user and member profile (INACTIVE status)."""
    from sqlalchemy.exc import IntegrityError
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting user registration for email: {email}")
    
    # Check if user already exists by email
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        logger.warning(f"Registration attempt with existing email: {email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if NRC number already exists (if provided)
    nrc_number = kwargs.get('nrc_number')
    if nrc_number:
        existing_nrc = db.query(User).filter(User.nrc_number == nrc_number).first()
        if existing_nrc:
            logger.warning(f"Registration attempt with existing NRC: {nrc_number}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="NRC number already registered"
            )
    
    # Create user
    logger.info(f"Creating User object for {email}")
    user = User(
        email=email,
        password_hash=get_password_hash(password),
        first_name=first_name,
        last_name=last_name,
        **kwargs
    )
    db.add(user)
    
    try:
        logger.info(f"Flushing user to database to get user.id")
        db.flush()  # Get user.id
        logger.info(f"User created with ID: {user.id}")
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"IntegrityError creating user: {error_msg}", exc_info=True)
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
    except Exception as e:
        db.rollback()
        error_str = str(e)
        logger.error(f"Unexpected error creating user: {error_str}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {error_str}"
        )
    
    # Create member profile with INACTIVE status
    try:
        logger.info(f"Creating MemberProfile for user_id: {user.id} with status: {MemberStatus.INACTIVE}")
        logger.info(f"MemberStatus.INACTIVE value: {MemberStatus.INACTIVE.value}")
        logger.info(f"MemberStatus.INACTIVE type: {type(MemberStatus.INACTIVE)}")
        
        member_profile = MemberProfile(
            user_id=user.id,
            status=MemberStatus.INACTIVE
        )
        logger.info(f"MemberProfile object created, adding to session")
        db.add(member_profile)
        logger.info(f"Committing member profile to database")
        db.commit()
        logger.info(f"Member profile committed successfully, refreshing user")
        db.refresh(user)
        logger.info(f"User registration completed successfully for {email}")
        return user
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"IntegrityError creating member profile: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create member profile. Please try again."
        )
    except Exception as e:
        db.rollback()
        error_str = str(e)
        error_type = type(e).__name__
        logger.error(f"Error creating member profile - Type: {error_type}, Message: {error_str}", exc_info=True)
        
        # Log the full exception details
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"Full traceback:\n{tb_str}")
        
        # Check if the error is related to enum value
        error_lower = error_str.lower()
        if 'inactive' in error_lower or 'memberstatus' in error_lower or 'invalid input value for enum' in error_lower or 'enum' in error_lower:
            logger.error("Detected enum-related error. Database migration may be required.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database migration required. Please run: alembic upgrade head. Error: " + error_str
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create member profile: {error_str} (Type: {error_type})"
        )


def create_access_token_for_user(user: User) -> str:
    """Create access token for user."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
