"""
Create a default admin user.
Usage: python scripts/create_admin.py
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.db.base import SessionLocal
from app.models.user import User
from app.models.role import Role, UserRole
import uuid
import bcrypt


def create_admin(email: str = "admin@villagebank.com", password: str = "admin123", first_name: str = "Admin", last_name: str = "User"):
    """Create an admin user with Admin role."""
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"User with email {email} already exists!")
            return
        
        # Get Admin role
        admin_role = db.query(Role).filter(Role.name == "Admin").first()
        if not admin_role:
            print("Admin role not found! Please run seed_data.py first.")
            return
        
        # Create user with hashed password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(
            id=uuid.uuid4(),
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            approved=True  # Admin is auto-approved
        )
        db.add(user)
        db.flush()
        
        # Assign Admin role
        user_role = UserRole(
            user_id=user.id,
            role_id=admin_role.id,
            assigned_by=user.id  # Self-assigned for initial admin
        )
        db.add(user_role)
        
        db.commit()
        print(f"✅ Admin user created successfully!")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Role: Admin")
        print(f"\n⚠️  Please change the password after first login!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating admin user: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create a default admin user")
    parser.add_argument("--email", default="admin@villagebank.com", help="Admin email")
    parser.add_argument("--password", default="admin123", help="Admin password")
    parser.add_argument("--first-name", default="Admin", help="First name")
    parser.add_argument("--last-name", default="User", help="Last name")
    
    args = parser.parse_args()
    
    create_admin(
        email=args.email,
        password=args.password,
        first_name=args.first_name,
        last_name=args.last_name
    )
