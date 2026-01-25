# Database Cleanup Script

## Overview

The `clean_database.py` script removes all user-entered data from the database while preserving system configuration, admin user, and roles.

## What Gets Preserved

✅ **System Configuration:**
- Admin user account
- All roles (Admin, Chairman, Treasurer, etc.)
- Core ledger accounts (organization-level accounts like BANK_CASH, INTEREST_INCOME, etc.)
- System settings
- Policies (interest policies, credit rating schemes, borrowing limits)
- Penalty types (system-defined)
- Constitution documents
- AI document chunks and embeddings
- VB Group configuration

## What Gets Deleted

❌ **User Data:**
- All member profiles
- All user accounts (except admin)
- All user roles (except admin's roles)
- All cycles
- All declarations
- All deposit proofs and approvals
- All loan applications and loans
- All repayments
- All penalty records
- All journal entries and journal lines
- All member-specific ledger accounts
- All member credit ratings
- All collateral data
- All AI audit logs
- All migration staging data

## Usage

### Dry Run (Recommended First)

Test what would be deleted without actually deleting anything:

```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
python scripts/clean_database.py --dry-run
```

### Actual Cleanup

⚠️ **WARNING: This action cannot be undone!**

```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
python scripts/clean_database.py
```

The script will:
1. Detect the admin user automatically
2. Show you a count of records to be deleted
3. Ask for confirmation before proceeding
4. Delete all user data in the correct order (respecting foreign key constraints)
5. Preserve admin user and system configuration

## Admin User Detection

The script automatically finds the admin user by:
1. Looking for a user with the "Admin" role assigned
2. If not found, looking for a user with email containing "admin"
3. If still not found, looking for a user with legacy role field set to "admin"

If no admin is found, the script will warn you and ask if you want to continue anyway.

## Safety Features

- **Dry-run mode**: Test without making changes
- **Confirmation prompt**: Requires explicit "yes" to proceed
- **Transaction rollback**: If any error occurs, all changes are rolled back
- **Foreign key handling**: Deletes in correct order to avoid constraint violations
- **Admin preservation**: Automatically preserves admin user and their roles

## After Cleanup

After running the cleanup script:

1. **Re-run setup scripts** (if needed):
   ```bash
   python scripts/setup_ledger_accounts.py  # Recreate member accounts structure
   ```

2. **Verify admin access**: Log in with admin credentials to ensure everything works

3. **Create test data**: Start fresh with new members, cycles, etc.

## Example Output

```
============================================================
LUBOSS 95 - Database Cleanup Script
============================================================

This script will remove all user-entered data while preserving:
  - Admin user account
  - All system roles
  - System configuration (policies, settings)
  - Core ledger account structure
  - System documents (constitution, AI documents)

⚠️  WARNING: This action cannot be undone!

Counting records to be deleted...

Records to be deleted:
  member_profiles: 25
  declarations: 150
  deposit_proofs: 120
  ...
  
Total users: 30
Admin user will be preserved

⚠️  This will DELETE ALL USER DATA. Continue? (yes/no): yes

Starting cleanup...
------------------------------------------------------------
1. Deleting journal lines...
   ✓ Deleted journal lines
2. Deleting journal entries...
   ✓ Deleted journal entries
...
✅ DATABASE CLEANUP COMPLETED SUCCESSFULLY
```

## Troubleshooting

### Error: "No admin user found"
- Make sure you have at least one user with Admin role
- Or create an admin user first: `python scripts/create_admin.py`

### Error: Foreign key constraint violation
- The script handles foreign keys automatically
- If you see this error, it's a bug - please report it

### Error: Database connection failed
- Make sure your database is running
- Check your `.env` file has correct `DATABASE_URL`

## Notes

- The script uses database transactions - if anything fails, all changes are rolled back
- Member-specific ledger accounts are deleted, but core organization accounts are preserved
- The script is idempotent - safe to run multiple times (will just report 0 records if already clean)
