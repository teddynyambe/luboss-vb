from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.schemas.auth import UserRegister, UserLogin, Token, UserResponse, UserProfileUpdate, PasswordChange, PasswordResetRequest, PasswordReset
from app.services.auth import authenticate_user, create_user, create_access_token_for_user
from app.core.dependencies import get_current_user
from app.core.security import verify_password, get_password_hash
from app.services.rbac import get_user_roles
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user (creates member_profile with INACTIVE status)."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== REGISTRATION REQUEST START ===")
    logger.info(f"Email: {user_data.email}")
    logger.info(f"First Name: {user_data.first_name}")
    logger.info(f"Last Name: {user_data.last_name}")
    logger.info(f"Has NRC: {bool(user_data.nrc_number)}")
    
    try:
        user = create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone_number=user_data.phone_number,
            nrc_number=user_data.nrc_number,
            physical_address=user_data.physical_address,
            bank_account=user_data.bank_account,
            bank_name=user_data.bank_name,
            bank_branch=user_data.bank_branch,
            first_name_next_of_kin=user_data.first_name_next_of_kin,
            last_name_next_of_kin=user_data.last_name_next_of_kin,
            phone_number_next_of_kin=user_data.phone_number_next_of_kin
        )
        logger.info(f"Registration successful for {user_data.email}, returning response")
        return UserResponse(
            id=str(user.id),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            approved=user.approved
        )
    except HTTPException:
        # Re-raise HTTP exceptions (already have proper error messages)
        logger.error(f"HTTPException during registration for {user_data.email}")
        raise
    except Exception as e:
        # Log the full error for debugging
        import traceback
        error_type = type(e).__name__
        error_msg = str(e)
        tb_str = traceback.format_exc()
        
        logger.error(f"=== REGISTRATION FAILED ===")
        logger.error(f"Email: {user_data.email}")
        logger.error(f"Error Type: {error_type}")
        logger.error(f"Error Message: {error_msg}")
        logger.error(f"Full Traceback:\n{tb_str}")
        logger.error(f"=== END REGISTRATION ERROR ===")
        
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {error_msg} (Type: {error_type})"
        )


@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login and get JWT token."""
    from app.core.audit import write_audit_log
    user = authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    access_token = create_access_token_for_user(user)
    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
    user_role = user.role.value if user.role else "member"
    write_audit_log(user_name=user_name, user_role=user_role, action="Login", details=f"email={user.email}")
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """Record logout in audit log (token invalidation is handled client-side)."""
    from app.core.audit import write_audit_log
    user_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email
    user_role = current_user.role.value if current_user.role else "member"
    write_audit_log(user_name=user_name, user_role=user_role, action="Logout", details=f"email={current_user.email}")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user information including roles."""
    roles = get_user_roles(current_user, db)
    # If no roles from RBAC system, fall back to legacy role enum
    if not roles and current_user.role:
        # Map legacy enum to role name (capitalize first letter)
        legacy_role = current_user.role.value.capitalize()
        roles = [legacy_role]
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        approved=current_user.approved,
        roles=roles if roles else None,
        phone_number=current_user.phone_number,
        nrc_number=current_user.nrc_number,
        physical_address=current_user.physical_address,
        bank_account=current_user.bank_account,
        bank_name=current_user.bank_name,
        bank_branch=current_user.bank_branch,
        first_name_next_of_kin=current_user.first_name_next_of_kin,
        last_name_next_of_kin=current_user.last_name_next_of_kin,
        phone_number_next_of_kin=current_user.phone_number_next_of_kin
    )


@router.put("/profile", response_model=UserResponse)
def update_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile information."""
    # Update only provided fields
    if profile_data.first_name is not None:
        current_user.first_name = profile_data.first_name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
    if profile_data.phone_number is not None:
        current_user.phone_number = profile_data.phone_number
    if profile_data.nrc_number is not None:
        # Check if NRC number is already taken by another user
        existing_user = db.query(User).filter(
            User.nrc_number == profile_data.nrc_number,
            User.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="NRC number already registered to another user"
            )
        current_user.nrc_number = profile_data.nrc_number
    if profile_data.physical_address is not None:
        current_user.physical_address = profile_data.physical_address
    if profile_data.bank_account is not None:
        current_user.bank_account = profile_data.bank_account
    if profile_data.bank_name is not None:
        current_user.bank_name = profile_data.bank_name
    if profile_data.bank_branch is not None:
        current_user.bank_branch = profile_data.bank_branch
    if profile_data.first_name_next_of_kin is not None:
        current_user.first_name_next_of_kin = profile_data.first_name_next_of_kin
    if profile_data.last_name_next_of_kin is not None:
        current_user.last_name_next_of_kin = profile_data.last_name_next_of_kin
    if profile_data.phone_number_next_of_kin is not None:
        current_user.phone_number_next_of_kin = profile_data.phone_number_next_of_kin
    
    try:
        db.commit()
        db.refresh(current_user)
        roles = get_user_roles(current_user, db)
        # If no roles from RBAC system, fall back to legacy role enum
        if not roles and current_user.role:
            # Map legacy enum to role name (capitalize first letter)
            legacy_role = current_user.role.value.capitalize()
            roles = [legacy_role]
        return UserResponse(
            id=str(current_user.id),
            email=current_user.email,
            first_name=current_user.first_name,
            last_name=current_user.last_name,
            approved=current_user.approved,
            roles=roles if roles else None,
            phone_number=current_user.phone_number,
            nrc_number=current_user.nrc_number,
            physical_address=current_user.physical_address,
            bank_account=current_user.bank_account,
            bank_name=current_user.bank_name,
            bank_branch=current_user.bank_branch,
            first_name_next_of_kin=current_user.first_name_next_of_kin,
            last_name_next_of_kin=current_user.last_name_next_of_kin,
            phone_number_next_of_kin=current_user.phone_number_next_of_kin
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.post("/change-password")
def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user's password."""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Validate new password
    if len(password_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long"
        )
    
    # Update password
    current_user.password_hash = get_password_hash(password_data.new_password)
    
    try:
        db.commit()
        return {"message": "Password changed successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change password: {str(e)}"
        )


@router.post("/forgot-password")
def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """Initiate a password reset by sending an email with a reset link."""
    import secrets
    import hashlib
    from datetime import datetime, timedelta
    from app.core.email import send_password_reset_email
    from app.core.config import settings

    generic_response = {"message": "If that email is registered, a reset link has been sent."}

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        return generic_response

    token = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    user.password_reset_token = hashed
    user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate password reset: {str(e)}"
        )

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    first_name = user.first_name or "Member"
    try:
        send_password_reset_email(to_email=user.email, reset_link=reset_link, first_name=first_name)
    except Exception:
        pass  # Email failure is logged in the utility; don't expose it to the caller

    return generic_response


@router.post("/reset-password")
def reset_password(data: PasswordReset, db: Session = Depends(get_db)):
    """Reset a user's password using a valid reset token."""
    import hashlib
    from datetime import datetime
    from app.core.security import get_password_hash

    if len(data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )

    hashed = hashlib.sha256(data.token.encode()).hexdigest()
    user = db.query(User).filter(User.password_reset_token == hashed).first()

    if not user or user.password_reset_expires is None or user.password_reset_expires < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    user.password_hash = get_password_hash(data.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None

    try:
        db.commit()
        return {"message": "Password reset successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset password: {str(e)}"
        )
