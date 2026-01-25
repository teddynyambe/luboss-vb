from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from werkzeug.security import check_password_hash as werkzeug_check_password_hash
from app.core.config import settings


def _verify_scrypt_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a scrypt hash using werkzeug (Flask's password hashing).
    
    Werkzeug's check_password_hash automatically handles scrypt format:
    Format: scrypt:N:r:p$base64_salt$hex_hash
    Example: scrypt:32768:8:1$gvdTNS8fYszatxAm$fbd4f61b45b0c7867b92155095340379a46be8c535bdb1523b8a4396586b6a95a81c0bfc679f4115f7e359861f3bf84012406eb6e436f6d31b0e6d516f67065a
    """
    try:
        # Werkzeug's check_password_hash handles scrypt format automatically
        return werkzeug_check_password_hash(hashed_password, plain_password)
    except Exception as e:
        # Log the error for debugging (but don't expose it to caller)
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Scrypt verification error: {e}", exc_info=True)
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    Supports both legacy scrypt format and current bcrypt format.
    """
    if not plain_password or not hashed_password:
        return False
    
    # Check if it's a scrypt hash (legacy format)
    if hashed_password.startswith('scrypt:'):
        return _verify_scrypt_password(plain_password, hashed_password)
    
    # Otherwise, treat as bcrypt hash (current format)
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
