# Migrate Data to Production Server

## Overview

This guide shows how to migrate data from your local/development database to the production server.

## Option 1: Export/Import Using pg_dump (Recommended)

### Step 1: Export Data from Local Database

On your local machine:

```bash
# Export only data (no schema) from local database
pg_dump -h localhost -U your_local_user -d village_bank \
  --data-only \
  --no-owner \
  --no-privileges \
  --file=local_data.sql

# Or export specific tables only
pg_dump -h localhost -U your_local_user -d village_bank \
  --data-only \
  --table=user \
  --table=member_profile \
  --table=role \
  --table=user_role \
  --no-owner \
  --no-privileges \
  --file=user_data.sql
```

### Step 2: Transfer to Server

```bash
# Copy the SQL file to server
scp local_data.sql teddy@luboss95vb.com:/tmp/

# Or if you want to exclude certain tables (like staging tables)
pg_dump -h localhost -U your_local_user -d village_bank \
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

scp production_data.sql teddy@luboss95vb.com:/tmp/
```

### Step 3: Import on Production Server

SSH into server and import:

```bash
# SSH into server
ssh teddy@luboss95vb.com

# Import the data
psql -U luboss -d village_bank -f /tmp/production_data.sql

# Or with postgres user
sudo -u postgres psql -d village_bank -f /tmp/production_data.sql
```

## Option 2: Export Specific Tables Only

If you only want to migrate users and related data:

```bash
# Export user-related tables
pg_dump -h localhost -U your_local_user -d village_bank \
  --data-only \
  --table=user \
  --table=member_profile \
  --table=user_role \
  --table=role \
  --no-owner \
  --no-privileges \
  --file=user_migration.sql

# Transfer and import
scp user_migration.sql teddy@luboss95vb.com:/tmp/
ssh teddy@luboss95vb.com
sudo -u postgres psql -d village_bank -f /tmp/user_migration.sql
```

## Option 3: Use Seed Script (For Initial Setup)

If you just need to seed initial data (roles, ledger accounts, etc.):

```bash
# On production server
cd /var/www/luboss-vb
source app/venv/bin/activate
python scripts/seed_data.py
```

## Option 4: Manual SQL Export/Import

### Export from Local

```bash
# Connect to local database
psql -d village_bank

# Export users
\copy (SELECT * FROM "user") TO '/tmp/users.csv' WITH CSV HEADER;

# Export member profiles
\copy (SELECT * FROM member_profile) TO '/tmp/member_profiles.csv' WITH CSV HEADER;

# Exit
\q
```

### Import to Production

```bash
# On production server
sudo -u postgres psql -d village_bank

# Import users
\copy "user" FROM '/tmp/users.csv' WITH CSV HEADER;

# Import member profiles
\copy member_profile FROM '/tmp/member_profiles.csv' WITH CSV HEADER;

# Exit
\q
```

## Option 5: Create Admin User Manually

If you just need to create an admin user to get started:

```bash
# On production server
cd /var/www/luboss-vb
source app/venv/bin/activate
python scripts/create_admin.py
```

Or manually:

```bash
# Generate password hash (Python)
python3 -c "
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
print(pwd_context.hash('your_password_here'))
"

# Then insert into database
sudo -u postgres psql -d village_bank -c "
INSERT INTO \"user\" (id, email, first_name, last_name, password_hash, role, approved, date_joined)
VALUES (
    gen_random_uuid(),
    'admin@example.com',
    'Admin',
    'User',
    'hashed_password_from_above',
    'admin',
    true,
    NOW()
);
"
```

## Complete Migration Script

Here's a complete script to migrate all user data:

```bash
#!/bin/bash
# migrate_to_production.sh

LOCAL_DB="postgresql://your_local_user@localhost/village_bank"
PROD_DB="postgresql://luboss:pAssw0rd.123@127.0.0.1:5432/village_bank"
SERVER="teddy@luboss95vb.com"

echo "Exporting data from local database..."
pg_dump $LOCAL_DB \
  --data-only \
  --exclude-table=stg_members \
  --exclude-table=stg_deposits \
  --exclude-table=stg_loans \
  --exclude-table=stg_repayments \
  --exclude-table=stg_penalties \
  --exclude-table=stg_cycles \
  --no-owner \
  --no-privileges \
  --file=/tmp/production_data.sql

echo "Copying to server..."
scp /tmp/production_data.sql $SERVER:/tmp/

echo "Importing on server..."
ssh $SERVER "sudo -u postgres psql -d village_bank -f /tmp/production_data.sql"

echo "Migration complete!"
```

## Important Notes

1. **Backup First**: Always backup production database before importing:
   ```bash
   sudo -u postgres pg_dump -d village_bank > /tmp/village_bank_backup_$(date +%Y%m%d).sql
   ```

2. **Check Data**: After importing, verify:
   ```bash
   sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"
   ```

3. **Foreign Keys**: Make sure to import in the correct order to satisfy foreign key constraints:
   - Roles first
   - Users
   - Member profiles
   - User roles
   - Other dependent data

4. **IDs**: If you're migrating from a different system, you may need to handle ID mappings using the `id_map_*` tables.

## Quick Start: Just Create an Admin User

If you just need to get started quickly:

```bash
# On production server
cd /var/www/luboss-vb
source app/venv/bin/activate
python scripts/create_admin.py
```

This will create an admin user you can use to log in and manage the system.
