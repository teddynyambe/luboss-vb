"""simplify_member_status_to_active_inactive

Revision ID: simplify_member_status
Revises: add_chairman_role
Create Date: 2026-01-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'simplify_member_status'
down_revision: Union[str, None] = 'add_chairman_role'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'INACTIVE' to the memberstatus enum if it doesn't exist
    # PostgreSQL requires enum additions to be committed before use
    # We'll use a DO block to check and add if needed, then commit
    connection = op.get_bind()
    
    # Check if INACTIVE already exists and add it if not
    # Using a DO block that commits the enum addition
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'INACTIVE' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'memberstatus')
            ) THEN
                ALTER TYPE memberstatus ADD VALUE 'INACTIVE';
            END IF;
        END $$;
    """)
    
    # Commit the enum addition (DDL auto-commits, but we ensure it)
    connection.commit()
    
    # Now we can use INACTIVE in updates
    # Update existing records: PENDING -> INACTIVE, SUSPENDED -> INACTIVE
    op.execute("""
        UPDATE member_profile 
        SET status = 'INACTIVE'::memberstatus 
        WHERE status IN ('PENDING'::memberstatus, 'SUSPENDED'::memberstatus)
    """)
    
    # Update member_status_history records
    op.execute("""
        UPDATE member_status_history 
        SET old_status = 'INACTIVE'::memberstatus 
        WHERE old_status IN ('PENDING'::memberstatus, 'SUSPENDED'::memberstatus)
    """)
    
    op.execute("""
        UPDATE member_status_history 
        SET new_status = 'INACTIVE'::memberstatus 
        WHERE new_status IN ('PENDING'::memberstatus, 'SUSPENDED'::memberstatus)
    """)
    
    # Update default value for new member profiles
    # Note: We can't change the default directly, but new records will use INACTIVE from the model


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values directly
    # This would require recreating the enum and updating all references
    # For safety, we'll leave a comment here
    # If downgrade is needed, it would require:
    # 1. Create new enum with PENDING and SUSPENDED
    # 2. Update all member_profile.status and member_status_history columns
    # 3. Drop old enum and rename new one
    
    # Revert records back (but we don't know which were PENDING vs SUSPENDED)
    # This is a lossy operation - we'll set all INACTIVE to PENDING
    op.execute("""
        UPDATE member_profile 
        SET status = 'PENDING'::memberstatus 
        WHERE status = 'INACTIVE'::memberstatus
    """)
    
    op.execute("""
        UPDATE member_status_history 
        SET old_status = 'PENDING'::memberstatus 
        WHERE old_status = 'INACTIVE'::memberstatus
    """)
    
    op.execute("""
        UPDATE member_status_history 
        SET new_status = 'PENDING'::memberstatus 
        WHERE new_status = 'INACTIVE'::memberstatus
    """)
    
    # Note: We cannot remove 'INACTIVE' from the enum in PostgreSQL
    pass
