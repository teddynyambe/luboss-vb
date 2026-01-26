# Step-by-Step: Fresh Database Migration

## Overview

This guide will:
1. Drop the production database
2. Create a new empty database
3. Run migrations to create schema
4. Export all data from local database
5. Import data to production

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

## Step 2: Drop and Recreate Database

**On production server:**

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# In psql, run:
DROP DATABASE village_bank;
CREATE DATABASE village_bank OWNER luboss;
GRANT ALL PRIVILEGES ON DATABASE village_bank TO luboss;

# Exit psql
\q
```

## Step 3: Enable Extensions

**On production server:**

```bash
# Enable pgvector extension
sudo -u postgres psql -d village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Verify
sudo -u postgres psql -d village_bank -c "\dx"
```

## Step 4: Run Migrations

**On production server:**

```bash
cd /var/www/luboss-vb
source app/venv/bin/activate

# Run all migrations to create schema
alembic upgrade head

# Verify tables were created
sudo -u postgres psql -d village_bank -c "\dt" | head -20
```

## Step 5: Export Data from Local Database

**On your local machine:**

```bash
# Navigate to project directory
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb

# Export ALL data (excluding staging tables)
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

# Check file was created
ls -lh production_data.sql
```

## Step 6: Transfer to Server

**On your local machine:**

```bash
# Copy SQL file to server
scp production_data.sql teddy@luboss95vb.com:/tmp/
```

## Step 7: Import Data to Production

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

## Step 8: Verify Data

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
UNION ALL SELECT 'loan', COUNT(*) FROM loan;
EOF

# List some users
sudo -u postgres psql -d village_bank -c "SELECT email, first_name, last_name FROM \"user\" LIMIT 10;"
```

## Step 9: Restart Backend

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

echo "=== Step 5: Running migrations ==="
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic upgrade head
echo "✅ Migrations complete"

echo "=== Step 6: Importing data ==="
sudo -u postgres psql -d village_bank << 'EOF'
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF
echo "✅ Data imported"

echo "=== Step 7: Verifying ==="
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) as user_count FROM \"user\";"

echo "=== Step 8: Restarting backend ==="
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

# Run migrations
cd /var/www/luboss-vb && source app/venv/bin/activate && alembic upgrade head

# Import data
sudo -u postgres psql -d village_bank << 'EOF'
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF

# Verify
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"

# Restart backend
sudo systemctl restart luboss-backend
```

## Important Notes

1. **Backup First**: Always backup before dropping!
2. **Check File Size**: Make sure `production_data.sql` was created and has content
3. **Import Errors**: Some errors during import are OK (missing tables, enum mismatches) - the important data (users, etc.) should import
4. **Verify After**: Always check that users were imported before considering it complete

## Troubleshooting

If import fails:
- Check file was transferred: `ls -lh /tmp/production_data.sql`
- Try importing without FK disable first
- Check PostgreSQL logs: `sudo tail -f /var/log/postgresql/postgresql-*.log`
