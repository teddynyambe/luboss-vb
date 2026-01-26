# Fix Import Issues

## Issues Found

1. ✅ **Many tables imported successfully** (COPY statements show rows copied)
2. ❌ **Missing table**: `credit_rating_interest_range` doesn't exist yet
3. ❌ **Enum mismatch**: `penaltyrecordstatus` enum values don't match
4. ⚠️ **Dump file format issues**: Some backslash commands in the dump

## Step 1: Check What Was Imported

```bash
# Check if users were imported
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"

# Check other key tables
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM member_profile;"
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM role;"
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM ledger_account;"
```

## Step 2: Fix Missing Table

The `credit_rating_interest_range` table should be created by migrations. Check if migrations completed:

```bash
# Check current migration version
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic current

# Check if the table exists
sudo -u postgres psql -d village_bank -c "\d credit_rating_interest_range"
```

If the table doesn't exist, the migration that creates it might not have run. Check which migration creates it.

## Step 3: Fix Enum Mismatch

The enum in your local database has different values than production. Check what enum exists:

```bash
# Check current enum values
sudo -u postgres psql -d village_bank -c "
SELECT enumlabel 
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus')
ORDER BY enumsortorder;"
```

If it's missing "APPROVED", you may need to:
1. Skip importing penalty_record data, OR
2. Update the enum first, then import

## Step 4: Clean Import (Recommended)

Instead of fixing the problematic dump, create a cleaner export:

### Export Only Essential Tables

```bash
# On local machine - export only user-related tables
pg_dump -h localhost -U teddy -d village_bank \
  --data-only \
  --table=user \
  --table=member_profile \
  --table=role \
  --table=user_role \
  --table=ledger_account \
  --table=interest_policy \
  --table=credit_rating_scheme \
  --table=credit_rating_tier \
  --no-owner \
  --no-privileges \
  --file=essential_data.sql

# Transfer and import
scp essential_data.sql teddy@luboss95vb.com:/tmp/
ssh teddy@luboss95vb.com
sudo -u postgres psql -d village_bank -f /tmp/essential_data.sql
```

## Quick Fix: Check What You Have

First, see what was successfully imported:

```bash
# On production server
sudo -u postgres psql -d village_bank << 'EOF'
SELECT 'user' as table_name, COUNT(*) as row_count FROM "user"
UNION ALL
SELECT 'member_profile', COUNT(*) FROM member_profile
UNION ALL
SELECT 'role', COUNT(*) FROM role
UNION ALL
SELECT 'user_role', COUNT(*) FROM user_role
UNION ALL
SELECT 'ledger_account', COUNT(*) FROM ledger_account;
EOF
```

If users were imported, you're good to go! The errors are for tables that either:
- Don't exist yet (will be created by migrations)
- Have schema differences (can be fixed later)

## Recommended: Use Seed Script Instead

For a clean start, use the seed script:

```bash
# On production server
cd /var/www/luboss-vb
source app/venv/bin/activate

# Seed system data
python scripts/seed_data.py

# Create admin user
python scripts/create_admin.py
```

This ensures all system data is correct and creates a working admin user.
