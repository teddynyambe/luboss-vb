# Exporting and Importing Penalty Record Data

This guide shows how to export `penalty_record` data from your local database and import it to production.

## Prerequisites

1. **Local database** has penalty records you want to export
2. **Production database** has:
   - Members (for `member_id` foreign key)
   - Penalty types (for `penalty_type_id` foreign key)
   - Users (for `created_by` and `approved_by` foreign keys)

## Step 1: Export from Local Database

### Option A: Using the Export Script

```bash
# From your local machine
cd /path/to/luboss-vb
chmod +x scripts/export_penalty_data.sh

# Set your local DATABASE_URL if needed
export DATABASE_URL="postgresql://username:password@localhost:5432/village_bank"

# Run export
./scripts/export_penalty_data.sh
```

This creates two files:
- `penalty_records_export_TIMESTAMP.sql` - CSV format
- `penalty_records_export_TIMESTAMP_inserts.sql` - SQL INSERT statements

### Option B: Manual Export

```bash
# Connect to local database
psql postgresql://username:password@localhost:5432/village_bank

# Export to CSV
\copy (SELECT id, member_id, penalty_type_id, date_issued, status::text, created_by, approved_by, approved_at, journal_entry_id, notes FROM penalty_record ORDER BY date_issued) TO 'penalty_records.csv' WITH CSV HEADER;

# Or export as SQL INSERT statements
psql postgresql://username:password@localhost:5432/village_bank -t -A <<EOF > penalty_records_inserts.sql
SELECT 
    'INSERT INTO penalty_record (id, member_id, penalty_type_id, date_issued, status, created_by, approved_by, approved_at, journal_entry_id, notes) VALUES (' ||
    quote_literal(id::text) || ', ' ||
    quote_literal(member_id::text) || ', ' ||
    quote_literal(penalty_type_id::text) || ', ' ||
    quote_literal(date_issued::text) || ', ' ||
    quote_literal(status::text) || '::penaltyrecordstatus, ' ||
    quote_literal(created_by::text) || ', ' ||
    COALESCE(quote_literal(approved_by::text), 'NULL') || ', ' ||
    COALESCE(quote_literal(approved_at::text), 'NULL') || ', ' ||
    COALESCE(quote_literal(journal_entry_id::text), 'NULL') || ', ' ||
    COALESCE(quote_literal(notes), 'NULL') || ');'
FROM penalty_record
ORDER BY date_issued;
EOF
```

## Step 2: Verify Dependencies in Production

Before importing, ensure production has the required data:

```bash
# SSH to production server
ssh teddy@luboss95vb.com

# Check members
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM member_profile;"

# Check penalty types
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM penalty_type;"

# Check users
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"
```

**Important:** The `member_id`, `penalty_type_id`, `created_by`, and `approved_by` values in your export must exist in production, or the import will fail due to foreign key constraints.

## Step 3: Transfer Files to Production

```bash
# From your local machine
scp penalty_records_export_*_inserts.sql teddy@luboss95vb.com:/tmp/
```

## Step 4: Import to Production

### Option A: Using the Import Script

```bash
# SSH to production server
ssh teddy@luboss95vb.com

# Copy script to server (if not already there)
# Or run manually

cd /var/www/luboss-vb
chmod +x scripts/import_penalty_data.sh
./scripts/import_penalty_data.sh /tmp/penalty_records_export_TIMESTAMP_inserts.sql
```

### Option B: Manual Import

```bash
# SSH to production server
ssh teddy@luboss95vb.com

# Review the SQL file first
cat /tmp/penalty_records_export_TIMESTAMP_inserts.sql | head -20

# Import
sudo -u postgres psql -d village_bank -f /tmp/penalty_records_export_TIMESTAMP_inserts.sql

# Verify
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM penalty_record;"
sudo -u postgres psql -d village_bank -c "SELECT status, COUNT(*) FROM penalty_record GROUP BY status;"
```

## Step 5: Verify Import

```bash
# Check total count
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM penalty_record;"

# Check by status
sudo -u postgres psql -d village_bank -c "SELECT status, COUNT(*) FROM penalty_record GROUP BY status;"

# View sample records
sudo -u postgres psql -d village_bank -c "SELECT id, member_id, status, date_issued FROM penalty_record LIMIT 5;"
```

## Handling Foreign Key Issues

If you get foreign key constraint errors:

1. **Member IDs don't match:**
   - Export members first, or
   - Update member_id values in the SQL file to match production member IDs

2. **Penalty type IDs don't match:**
   - Export penalty types first, or
   - Update penalty_type_id values to match production

3. **User IDs don't match:**
   - Export users first, or
   - Update created_by/approved_by to use production user IDs

## Quick Export/Import Commands

### Export (Local)
```bash
psql $DATABASE_URL -c "\copy (SELECT * FROM penalty_record) TO 'penalty_records.csv' WITH CSV HEADER"
```

### Import (Production)
```bash
# First, ensure enum values match
sudo -u postgres psql -d village_bank -c "SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus');"

# Import with proper enum casting
sudo -u postgres psql -d village_bank <<EOF
SET session_replication_role = 'replica';
\copy penalty_record(id, member_id, penalty_type_id, date_issued, status, created_by, approved_by, approved_at, journal_entry_id, notes) FROM 'penalty_records.csv' WITH CSV HEADER;
UPDATE penalty_record SET status = status::text::penaltyrecordstatus;
SET session_replication_role = 'origin';
EOF
```

## Troubleshooting

### Error: "foreign key constraint violation"
- Ensure all referenced IDs exist in production
- Check member_profile, penalty_type, and user tables

### Error: "invalid input value for enum"
- Verify enum values match: `pending`, `approved`, `paid` (lowercase)
- Check: `SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus');`

### Error: "duplicate key value"
- Records with same ID already exist
- Either skip duplicates or delete existing records first

## Complete Example

```bash
# 1. Export from local
cd /path/to/luboss-vb
./scripts/export_penalty_data.sh

# 2. Transfer to production
scp penalty_records_export_*_inserts.sql teddy@luboss95vb.com:/tmp/

# 3. Import on production
ssh teddy@luboss95vb.com
cd /var/www/luboss-vb
./scripts/import_penalty_data.sh /tmp/penalty_records_export_*_inserts.sql

# 4. Verify
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*), status FROM penalty_record GROUP BY status;"
```
