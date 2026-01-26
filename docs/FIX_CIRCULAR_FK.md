# Fix: Circular Foreign Key Constraints in pg_dump

## Problem

When exporting data-only, pg_dump warns about circular foreign key constraints on `ledger_account` table. This happens when tables reference each other.

## Solution Options

### Option 1: Use --disable-triggers (Recommended)

When importing, disable triggers temporarily:

```bash
# On production server, import with triggers disabled
sudo -u postgres psql -d village_bank << EOF
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF
```

### Option 2: Export with Schema (Then Extract Data)

Export with schema, then extract only INSERT statements:

```bash
# Export with schema
pg_dump -h localhost -U teddy -d village_bank \
  --exclude-table=stg_members \
  --exclude-table=stg_deposits \
  --exclude-table=stg_loans \
  --exclude-table=stg_repayments \
  --exclude-table=stg_penalties \
  --exclude-table=stg_cycles \
  --no-owner \
  --no-privileges \
  --file=full_dump.sql

# Then extract only INSERT statements (data)
grep "^INSERT" full_dump.sql > production_data.sql
```

### Option 3: Import with Foreign Keys Disabled

```bash
# On production server
sudo -u postgres psql -d village_bank -c "SET session_replication_role = 'replica';"
sudo -u postgres psql -d village_bank -f /tmp/production_data.sql
sudo -u postgres psql -d village_bank -c "SET session_replication_role = 'origin';"
```

### Option 4: Ignore the Warning (Usually Works)

The warning is often harmless. Try importing normally first:

```bash
# The dump file was created successfully despite the warning
# Try importing it normally
sudo -u postgres psql -d village_bank -f /tmp/production_data.sql
```

If it fails with foreign key errors, then use Option 1 or 3.

## Complete Migration with FK Handling

```bash
# 1. Export (on local machine) - warning is OK
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

# 2. Transfer to server
scp production_data.sql teddy@luboss95vb.com:/tmp/

# 3. Import with FK handling (on server)
ssh teddy@luboss95vb.com
sudo -u postgres psql -d village_bank << 'EOF'
SET session_replication_role = 'replica';
\i /tmp/production_data.sql
SET session_replication_role = 'origin';
EOF

# 4. Verify
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"
```

The warning is usually safe to ignore - the dump file is still valid.
