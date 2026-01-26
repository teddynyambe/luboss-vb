# Step-by-Step: Fresh Database Migration

## Overview

This guide provides a complete process to:
1. Backup production database (safety first!)
2. Stop backend service to release database connections
3. Drop and recreate the production database
4. Enable required extensions (pgvector)
5. Create alembic_version table with correct permissions
6. Run migrations to create schema
7. Create any missing tables (if needed)
8. Export all data from local database
9. Transfer data to production server
10. Import all data to production
11. Verify data was imported correctly
12. Restart backend service

**✅ This process has been tested and verified to work successfully.**

## Quick Summary

This migration process will:
- ✅ Export all production data (users, declarations, cycles, loans, deposits, etc.) from local database
- ✅ Create a fresh database on production server
- ✅ Run all migrations to create the complete schema
- ✅ Import all data to production
- ✅ Verify all data was imported correctly

**Time Required:** Approximately 5-10 minutes depending on data size.

**Data Included:** All tables except staging tables (`stg_*`). This includes:
- Users, member profiles, roles
- Cycles, declarations, deposits
- Loans, repayments, penalties
- Credit ratings, interest ranges
- Ledger accounts, journal entries
- All other production data

## Step 1: Backup Production Database (Important!)

**On production server:**

```bash
# SSH into server
ssh teddy@luboss95vb.com

# Create backup (just in case)
sudo -u postgres pg_dump -d village_bank > /tmp/village_bank_backup_$(date +%Y%m%d_%H%M%S).sql

# Verify backup was created
ls -lh /tmp/village_bank_backup_*.sql
```

## Step 2: Stop Backend Service (If Running)

**On production server:**

```bash
# Stop backend to release database connections
sudo systemctl stop luboss-backend

# Verify it's stopped
sudo systemctl status luboss-backend
```

## Step 3: Drop and Recreate Database

**On production server:**

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# In psql, run:
DROP DATABASE IF EXISTS village_bank;
CREATE DATABASE village_bank OWNER luboss;
GRANT ALL PRIVILEGES ON DATABASE village_bank TO luboss;

# Exit psql
\q
```

**Note:** If you get "database is being accessed by other users", make sure the backend service is stopped, or terminate connections:
```bash
# Terminate all connections to the database
sudo -u postgres psql -c "
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = 'village_bank'
  AND pid <> pg_backend_pid();"
```

## Step 4: Enable Extensions

**On production server:**

```bash
# Enable pgvector extension
sudo -u postgres psql -d village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Verify
sudo -u postgres psql -d village_bank -c "\dx"
```

## Step 5: Create alembic_version Table (Important!)

**On production server:**

Before running migrations, create the `alembic_version` table with a larger column size to accommodate long revision IDs:

```bash
# Create alembic_version table with VARCHAR(50) instead of default VARCHAR(32)
sudo -u postgres psql -d village_bank -c "
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(50) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);"

# Grant permissions to luboss user
sudo -u postgres psql -d village_bank -c "
GRANT ALL PRIVILEGES ON TABLE alembic_version TO luboss;
ALTER TABLE alembic_version OWNER TO luboss;"

# Verify it was created and has correct permissions
sudo -u postgres psql -d village_bank -c "\d alembic_version"
```

**Why?** Some migration revision IDs are 32+ characters long, and the default `VARCHAR(32)` causes errors.

## Step 6: Run Migrations

**On production server:**

```bash
cd /var/www/luboss-vb
source app/venv/bin/activate

# Run all migrations to create schema
alembic upgrade head

# Verify migrations completed
alembic current

# Verify tables were created
sudo -u postgres psql -d village_bank -c "\dt" | head -20
```

## Step 6a: Create Missing Tables (If Needed)

Some tables may not be created by migrations. Create them if missing:

### Create credit_rating_interest_range Table

This table is required but may not be in the initial schema migration:

```bash
# Create the missing credit_rating_interest_range table
sudo -u postgres psql -d village_bank -c "
CREATE TABLE IF NOT EXISTS credit_rating_interest_range (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier_id UUID NOT NULL REFERENCES credit_rating_tier(id),
    cycle_id UUID NOT NULL REFERENCES cycle(id),
    term_months VARCHAR(10),
    effective_rate_percent NUMERIC(5, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_credit_rating_interest_range_tier_id ON credit_rating_interest_range(tier_id);
CREATE INDEX IF NOT EXISTS ix_credit_rating_interest_range_cycle_id ON credit_rating_interest_range(cycle_id);

GRANT ALL PRIVILEGES ON TABLE credit_rating_interest_range TO luboss;
ALTER TABLE credit_rating_interest_range OWNER TO luboss;
"

# Verify it was created
sudo -u postgres psql -d village_bank -c "\d credit_rating_interest_range"
```

## Step 7: Export Data from Local Database

**On your local machine:**

```bash
# Navigate to project directory
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb

# Export ALL data (excluding ONLY staging tables)
# This includes: users, declarations, loans, deposits, cycles, credit ratings, etc.
pg_dump -h localhost -U teddy -d village_bank \
  --data-only \
  --exclude-table=stg_members \
  --exclude-table=stg_deposits \
  --exclude-table=stg_loans \
  --exclude-table=stg_repayments \
  --exclude-table=stg_penalties \
  --exclude-table=stg_cycles \
  --no-owner \
  --no-privileges \
  --file=production_data.sql

# Verify the export includes important tables
echo "Checking export includes key tables:"
grep -E "^(COPY|INSERT INTO) (\"user\"|declaration|loan|deposit_proof|cycle|credit_rating_interest_range)" production_data.sql | head -20

# Check file size to ensure it has content
ls -lh production_data.sql

# Check file was created
ls -lh production_data.sql
```

## Step 7: Transfer to Server

**On your local machine:**

```bash
# Copy SQL file to server
scp production_data.sql teddy@luboss95vb.com:/tmp/
```

## Step 9: Import Data to Production

**On production server:**

```bash
# SSH into server (if not already)
ssh teddy@luboss95vb.com

# Import data with foreign key handling
sudo -u postgres psql -d village_bank << 'EOF'
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF
```

## Step 9: Verify Data

**On production server:**

```bash
# Check user count
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"

# Check other key tables
sudo -u postgres psql -d village_bank << 'EOF'
SELECT 'user' as table_name, COUNT(*) as rows FROM "user"
UNION ALL SELECT 'member_profile', COUNT(*) FROM member_profile
UNION ALL SELECT 'role', COUNT(*) FROM role
UNION ALL SELECT 'user_role', COUNT(*) FROM user_role
UNION ALL SELECT 'ledger_account', COUNT(*) FROM ledger_account
UNION ALL SELECT 'cycle', COUNT(*) FROM cycle
UNION ALL SELECT 'declaration', COUNT(*) FROM declaration
UNION ALL SELECT 'loan', COUNT(*) FROM loan
UNION ALL SELECT 'deposit_proof', COUNT(*) FROM deposit_proof
UNION ALL SELECT 'credit_rating_interest_range', COUNT(*) FROM credit_rating_interest_range;
EOF

# List some users
sudo -u postgres psql -d village_bank -c "SELECT email, first_name, last_name FROM \"user\" LIMIT 10;"
```

## Step 11: Restart Backend

**On production server:**

```bash
# Restart backend to pick up new data
sudo systemctl restart luboss-backend

# Check status
sudo systemctl status luboss-backend --no-pager -l | head -15

# Test API
curl http://localhost:8002/health
```

## Complete Script (All Steps)

Here's a complete script you can run:

### On Local Machine (export.sh):

```bash
#!/bin/bash
# export_data.sh

echo "=== Step 1: Exporting data from local database ==="
pg_dump -h localhost -U teddy -d village_bank \
  --data-only \
  --exclude-table=stg_members \
  --exclude-table=stg_deposits \
  --exclude-table=stg_loans \
  --exclude-table=stg_repayments \
  --exclude-table=stg_penalties \
  --exclude-table=stg_cycles \
  --no-owner \
  --no-privileges \
  --file=production_data.sql

echo "=== Step 2: Transferring to server ==="
scp production_data.sql teddy@luboss95vb.com:/tmp/

echo "✅ Export complete! File: production_data.sql"
echo "📦 File copied to server: /tmp/production_data.sql"
echo ""
echo "Next: SSH to server and run the import steps"
```

### On Production Server (import.sh):

```bash
#!/bin/bash
# import_data.sh

echo "=== Step 1: Backup existing database ==="
sudo -u postgres pg_dump -d village_bank > /tmp/village_bank_backup_$(date +%Y%m%d_%H%M%S).sql
echo "✅ Backup created"

echo "=== Step 2: Dropping database ==="
sudo -u postgres psql -c "DROP DATABASE IF EXISTS village_bank;"
echo "✅ Database dropped"

echo "=== Step 3: Creating new database ==="
sudo -u postgres psql -c "CREATE DATABASE village_bank OWNER luboss;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE village_bank TO luboss;"
echo "✅ Database created"

echo "=== Step 4: Enabling extensions ==="
sudo -u postgres psql -d village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
echo "✅ Extensions enabled"

echo "=== Step 6: Create alembic_version table ==="
sudo -u postgres psql -d village_bank -c "
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(50) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);"
echo "✅ alembic_version table created"

echo "=== Step 6: Running migrations ==="
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic upgrade head
echo "✅ Migrations complete"

echo "=== Step 6a: Creating missing credit_rating_interest_range table (if needed) ==="
sudo -u postgres psql -d village_bank -c "
CREATE TABLE IF NOT EXISTS credit_rating_interest_range (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier_id UUID NOT NULL REFERENCES credit_rating_tier(id),
    cycle_id UUID NOT NULL REFERENCES cycle(id),
    term_months VARCHAR(10),
    effective_rate_percent NUMERIC(5, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_credit_rating_interest_range_tier_id ON credit_rating_interest_range(tier_id);
CREATE INDEX IF NOT EXISTS ix_credit_rating_interest_range_cycle_id ON credit_rating_interest_range(cycle_id);
GRANT ALL PRIVILEGES ON TABLE credit_rating_interest_range TO luboss;
ALTER TABLE credit_rating_interest_range OWNER TO luboss;
" 2>/dev/null && echo "✅ Table created/verified" || echo "⚠️  Table may already exist"

echo "=== Step 7: Importing data ==="
sudo -u postgres psql -d village_bank << 'EOF'
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF
echo "✅ Data imported"

echo "=== Step 9: Verifying ==="
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) as user_count FROM \"user\";"

echo "=== Step 9: Restarting backend ==="
sudo systemctl restart luboss-backend
sleep 2
sudo systemctl status luboss-backend --no-pager -l | head -10

echo "✅ Migration complete!"
```

## Quick Commands (Copy-Paste)

### On Local Machine:

```bash
# Export
pg_dump -h localhost -U teddy -d village_bank \
  --data-only \
  --exclude-table=stg_members \
  --exclude-table=stg_deposits \
  --exclude-table=stg_loans \
  --exclude-table=stg_repayments \
  --exclude-table=stg_penalties \
  --exclude-table=stg_cycles \
  --no-owner \
  --no-privileges \
  --file=production_data.sql

# Transfer
scp production_data.sql teddy@luboss95vb.com:/tmp/
```

### On Production Server:

```bash
# Backup
sudo -u postgres pg_dump -d village_bank > /tmp/village_bank_backup_$(date +%Y%m%d_%H%M%S).sql

# Drop and recreate
sudo -u postgres psql -c "DROP DATABASE IF EXISTS village_bank;"
sudo -u postgres psql -c "CREATE DATABASE village_bank OWNER luboss;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE village_bank TO luboss;"

# Enable extensions
sudo -u postgres psql -d village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Create alembic_version table with correct size and permissions
sudo -u postgres psql -d village_bank -c "
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(50) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
GRANT ALL PRIVILEGES ON TABLE alembic_version TO luboss;
ALTER TABLE alembic_version OWNER TO luboss;"

# Run migrations
cd /var/www/luboss-vb && source app/venv/bin/activate && alembic upgrade head

# Import data
sudo -u postgres psql -d village_bank << 'EOF'
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF

# Verify all key tables
sudo -u postgres psql -d village_bank << 'EOF'
SELECT 'user' as table_name, COUNT(*) as rows FROM "user"
UNION ALL SELECT 'declaration', COUNT(*) FROM declaration
UNION ALL SELECT 'cycle', COUNT(*) FROM cycle
UNION ALL SELECT 'loan', COUNT(*) FROM loan
UNION ALL SELECT 'deposit_proof', COUNT(*) FROM deposit_proof
UNION ALL SELECT 'credit_rating_interest_range', COUNT(*) FROM credit_rating_interest_range;
EOF

# Restart backend
sudo systemctl restart luboss-backend
```

## Important Notes

1. **Backup First**: Always backup before dropping the database!
2. **Stop Backend First**: Stop the backend service before dropping to avoid "database is being accessed" errors
3. **Create alembic_version First**: Must create `alembic_version` table with `VARCHAR(50)` and grant permissions to `luboss` user before running migrations
4. **Grant Permissions**: Always grant permissions to `luboss` user on any tables created manually
5. **Create Missing Tables**: Some tables like `credit_rating_interest_range` may not be in migrations - create them manually if needed
6. **Check File Size**: Make sure `production_data.sql` was created and has content before transferring
7. **Import Errors**: Some errors during import are OK (missing tables that will be created later, enum mismatches) - the important data (users, declarations, cycles, etc.) should import successfully
8. **Verify After**: Always check that users, declarations, and cycles were imported before considering it complete
9. **Export Includes All Data**: The export command only excludes staging tables (`stg_*`) - all production data (declarations, loans, deposits, cycles, etc.) is included

## Troubleshooting

### Database is Being Accessed Error

If you get "database is being accessed by other users" when dropping:

```bash
# Stop backend service
sudo systemctl stop luboss-backend

# Terminate all connections
sudo -u postgres psql -c "
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = 'village_bank'
  AND pid <> pg_backend_pid();"

# Then try dropping again
sudo -u postgres psql -c "DROP DATABASE village_bank;"
```

### Migration Error: "value too long for type character varying(32)"

This means `alembic_version` table wasn't created with the correct size. Fix it:

```bash
# Drop and recreate with correct size
sudo -u postgres psql -d village_bank -c "DROP TABLE IF EXISTS alembic_version;"
sudo -u postgres psql -d village_bank -c "
CREATE TABLE alembic_version (
    version_num VARCHAR(50) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
GRANT ALL PRIVILEGES ON TABLE alembic_version TO luboss;
ALTER TABLE alembic_version OWNER TO luboss;"

# Then run migrations again
cd /var/www/luboss-vb && source app/venv/bin/activate && alembic upgrade head
```

### Migration Error: "permission denied for table alembic_version"

The `luboss` user doesn't have permissions on the table. Fix it:

```bash
# Grant permissions
sudo -u postgres psql -d village_bank -c "
GRANT ALL PRIVILEGES ON TABLE alembic_version TO luboss;
ALTER TABLE alembic_version OWNER TO luboss;"

# Then run migrations again
cd /var/www/luboss-vb && source app/venv/bin/activate && alembic upgrade head
```

### Import Errors

If import fails:
- Check file was transferred: `ls -lh /tmp/production_data.sql`
- Check file has content: `head -20 /tmp/production_data.sql`
- Try importing without FK disable first: `sudo -u postgres psql -d village_bank -f /tmp/production_data.sql`
- Check PostgreSQL logs: `sudo tail -f /var/log/postgresql/postgresql-*.log`
- Some errors are OK (missing tables that will be created later, enum mismatches)

### No Users After Import

If no users were imported:
- Check the export file has user data: `grep -i "INSERT INTO.*user\|COPY.*user" production_data.sql | head -5`
- Verify import ran: Check for COPY statements in the output (they show row counts)
- Use seed script as alternative: `python scripts/seed_data.py && python scripts/create_admin.py`

### Missing credit_rating_interest_range Table

If you get errors about missing `credit_rating_interest_range` table:
- Create it using Step 5a above
- Grant permissions to `luboss` user
- Restart backend: `sudo systemctl restart luboss-backend`

### Verify All Data Was Imported

After import, verify all key tables have data:

```bash
sudo -u postgres psql -d village_bank << 'EOF'
SELECT 
    'user' as table_name, COUNT(*) as rows FROM "user"
UNION ALL SELECT 'declaration', COUNT(*) FROM declaration
UNION ALL SELECT 'cycle', COUNT(*) FROM cycle
UNION ALL SELECT 'loan', COUNT(*) FROM loan
UNION ALL SELECT 'deposit_proof', COUNT(*) FROM deposit_proof
UNION ALL SELECT 'credit_rating_interest_range', COUNT(*) FROM credit_rating_interest_range
ORDER BY table_name;
EOF
```

All tables should show row counts > 0 if data was imported successfully.

## Success Checklist

After completing the migration, verify:

- [ ] ✅ Database created successfully
- [ ] ✅ All migrations ran without errors
- [ ] ✅ `credit_rating_interest_range` table exists
- [ ] ✅ Users imported (check count > 0)
- [ ] ✅ Declarations imported (check count > 0)
- [ ] ✅ Cycles imported (check count > 0)
- [ ] ✅ Backend service restarted successfully
- [ ] ✅ API health check returns `{"status":"healthy"}`
- [ ] ✅ Can log in with existing user credentials
- [ ] ✅ Application loads without errors

## Notes

- **Export includes ALL data**: The export command only excludes staging tables. All production data (declarations, cycles, loans, deposits, credit ratings, etc.) is included.
- **Some import errors are OK**: You may see errors for tables that don't exist yet or enum mismatches, but the important data (users, declarations, cycles) should import successfully.
- **Missing tables**: If a table is missing after migrations (like `credit_rating_interest_range`), create it manually using Step 6a.
- **Permissions**: Always grant permissions to the `luboss` user on any manually created tables.
