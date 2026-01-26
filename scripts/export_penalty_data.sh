#!/bin/bash
# Export penalty_record data from local database for import to production

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Exporting Penalty Record Data ==="
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  DATABASE_URL not set. Using default local connection."
    DATABASE_URL="postgresql://localhost:5432/village_bank"
fi

# Export file
EXPORT_FILE="penalty_records_export.sql"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_FILE_TIMESTAMPED="penalty_records_export_${TIMESTAMP}.sql"

echo "1. Checking if penalty_record table has data..."
COUNT=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM penalty_record;" | xargs)

if [ "$COUNT" = "0" ]; then
    echo "⚠️  No penalty records found in local database."
    exit 0
fi

echo "✅ Found $COUNT penalty records"
echo ""

echo "2. Exporting penalty_record data..."
echo "   This will export:"
echo "   - penalty_record table data"
echo "   - Related penalty_type data (if needed)"
echo ""

# Export penalty_record data with proper formatting
psql "$DATABASE_URL" <<EOF > "$EXPORT_FILE_TIMESTAMPED" 2>&1
-- Export penalty_record data
-- Generated: $(date)

-- First, check what we're exporting
\echo '-- Penalty records to export:'
SELECT COUNT(*) as total_records FROM penalty_record;
SELECT status, COUNT(*) as count FROM penalty_record GROUP BY status;

-- Export the data
\copy (SELECT id, member_id, penalty_type_id, date_issued, status::text, created_by, approved_by, approved_at, journal_entry_id, notes FROM penalty_record ORDER BY date_issued) TO STDOUT WITH CSV HEADER

EOF

# Also create a proper SQL insert file
echo ""
echo "3. Creating SQL insert statements..."
psql "$DATABASE_URL" -t -A -F"," <<EOF > "${EXPORT_FILE_TIMESTAMPED%.sql}_inserts.sql"
-- SQL INSERT statements for penalty_record
-- Generated: $(date)
-- 
-- Usage: Review this file, then run on production:
--   psql -d village_bank -f ${EXPORT_FILE_TIMESTAMPED%.sql}_inserts.sql

BEGIN;

-- Disable foreign key checks temporarily (if needed)
SET session_replication_role = 'replica';

-- Insert penalty records
$(psql "$DATABASE_URL" -t <<INNER_EOF
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
INNER_EOF
)

-- Re-enable foreign key checks
SET session_replication_role = 'origin';

COMMIT;
EOF

echo "✅ Export complete!"
echo ""
echo "Files created:"
echo "  1. ${EXPORT_FILE_TIMESTAMPED} - CSV format"
echo "  2. ${EXPORT_FILE_TIMESTAMPED%.sql}_inserts.sql - SQL INSERT statements"
echo ""
echo "Next steps:"
echo "  1. Review the SQL file: ${EXPORT_FILE_TIMESTAMPED%.sql}_inserts.sql"
echo "  2. Transfer to production server"
echo "  3. Run on production: psql -d village_bank -f ${EXPORT_FILE_TIMESTAMPED%.sql}_inserts.sql"
echo ""
echo "⚠️  Important: Make sure member_id, penalty_type_id, and created_by exist in production!"
