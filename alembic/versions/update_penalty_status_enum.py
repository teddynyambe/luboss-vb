"""update_penalty_status_enum

Revision ID: update_penalty_status
Revises: add_penalty_type_to_cycle_phase, simplify_member_status
Create Date: 2026-01-24 15:48:35.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'update_penalty_status'
down_revision: Union[str, None] = 'add_penalty_type_to_cycle_phase'  # Depends on one head; both heads should be merged first
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update penaltyrecordstatus enum
    # Strategy:
    # 1. Add 'PAID' value if it doesn't exist
    # 2. Update existing records: POSTED -> APPROVED, REJECTED -> PENDING
    # 3. Remove REJECTED and POSTED from enum (requires recreating enum)
    
    connection = op.get_bind()
    
    # Step 1: Add 'PAID' value to enum if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'PAID' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus')
            ) THEN
                ALTER TYPE penaltyrecordstatus ADD VALUE 'PAID';
            END IF;
        END $$;
    """)
    
    # Commit the enum addition
    connection.commit()
    
    # Step 2: Update existing records
    # POSTED -> APPROVED (these were approved but not yet paid)
    op.execute("""
        UPDATE penalty_record 
        SET status = 'APPROVED'::penaltyrecordstatus 
        WHERE status = 'POSTED'::penaltyrecordstatus
    """)
    
    # REJECTED -> PENDING (rejected penalties go back to pending for reconsideration)
    op.execute("""
        UPDATE penalty_record 
        SET status = 'PENDING'::penaltyrecordstatus 
        WHERE status = 'REJECTED'::penaltyrecordstatus
    """)
    
    # Step 3: Remove REJECTED and POSTED from enum
    # PostgreSQL doesn't support removing enum values directly, so we need to:
    # 1. Create a new enum with only the values we want (lowercase to match Python enum)
    # 2. Update the column to use the new enum (with case conversion)
    # 3. Drop the old enum and rename the new one
    
    # Create new enum with only pending, approved, paid (lowercase to match Python enum)
    op.execute("""
        CREATE TYPE penaltyrecordstatus_new AS ENUM ('pending', 'approved', 'paid');
    """)
    
    # Update the column to use the new enum, converting old uppercase values to lowercase
    op.execute("""
        ALTER TABLE penalty_record 
        ALTER COLUMN status TYPE penaltyrecordstatus_new 
        USING CASE 
            WHEN UPPER(status::text) = 'PENDING' THEN 'pending'::penaltyrecordstatus_new
            WHEN UPPER(status::text) IN ('APPROVED', 'POSTED') THEN 'approved'::penaltyrecordstatus_new
            WHEN UPPER(status::text) = 'PAID' THEN 'paid'::penaltyrecordstatus_new
            WHEN UPPER(status::text) = 'REJECTED' THEN 'pending'::penaltyrecordstatus_new
            ELSE 'pending'::penaltyrecordstatus_new
        END;
    """)
    
    # Drop the old enum
    op.execute("DROP TYPE penaltyrecordstatus")
    
    # Rename the new enum to the original name
    op.execute("ALTER TYPE penaltyrecordstatus_new RENAME TO penaltyrecordstatus")


def downgrade() -> None:
    # Revert the enum changes
    # Note: This is a lossy operation - we can't distinguish which PENDING were REJECTED
    # and which APPROVED were POSTED
    
    # Create enum with old values
    op.execute("""
        CREATE TYPE penaltyrecordstatus_old AS ENUM ('pending', 'approved', 'rejected', 'posted');
    """)
    
    # Update column
    op.execute("""
        ALTER TABLE penalty_record 
        ALTER COLUMN status TYPE penaltyrecordstatus_old 
        USING status::text::penaltyrecordstatus_old;
    """)
    
    # Drop new enum
    op.execute("DROP TYPE penaltyrecordstatus")
    
    # Rename old enum
    op.execute("ALTER TYPE penaltyrecordstatus_old RENAME TO penaltyrecordstatus")
    
    # Note: We cannot restore which records were REJECTED vs PENDING
    # or which were POSTED vs APPROVED, so all will remain as they are
