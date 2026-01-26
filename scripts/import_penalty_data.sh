#!/bin/bash
# Import penalty_record data to production database

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=== Importing Penalty Record Data ==="
echo ""

# Check if SQL file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <sql_file>"
    echo "Example: $0 penalty_records_export_20260126_120000_inserts.sql"
    exit 1
fi

SQL_FILE="$1"

if [ ! -f "$SQL_FILE" ]; then
    echo "❌ Error: File '$SQL_FILE' not found!"
    exit 1
fi

echo "1. Checking database connection..."
if ! sudo -u postgres psql -d village_bank -c "SELECT 1;" > /dev/null 2>&1; then
    echo "❌ Error: Cannot connect to database"
    exit 1
fi
echo "✅ Database connection OK"
echo ""

echo "2. Checking current penalty_record count..."
CURRENT_COUNT=$(sudo -u postgres psql -d village_bank -t -c "SELECT COUNT(*) FROM penalty_record;" | xargs)
echo "   Current records: $CURRENT_COUNT"
echo ""

echo "3. Validating SQL file..."
# Check if file contains INSERT statements
if ! grep -q "INSERT INTO penalty_record" "$SQL_FILE"; then
    echo "⚠️  Warning: File doesn't appear to contain INSERT statements"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo "✅ SQL file looks valid"
echo ""

echo "4. Checking for required dependencies..."
echo "   Checking if members exist..."
MEMBER_COUNT=$(sudo -u postgres psql -d village_bank -t -c "SELECT COUNT(*) FROM member_profile;" | xargs)
echo "   Members in production: $MEMBER_COUNT"

echo "   Checking if penalty_types exist..."
PENALTY_TYPE_COUNT=$(sudo -u postgres psql -d village_bank -t -c "SELECT COUNT(*) FROM penalty_type;" | xargs)
echo "   Penalty types in production: $PENALTY_TYPE_COUNT"

if [ "$MEMBER_COUNT" = "0" ] || [ "$PENALTY_TYPE_COUNT" = "0" ]; then
    echo ""
    echo "⚠️  Warning: Missing dependencies!"
    echo "   You need members and penalty types before importing penalty records."
    exit 1
fi
echo "✅ Dependencies OK"
echo ""

echo "5. Preview of what will be imported..."
# Count INSERT statements
INSERT_COUNT=$(grep -c "INSERT INTO penalty_record" "$SQL_FILE" || echo "0")
echo "   INSERT statements found: $INSERT_COUNT"
echo ""

read -p "Proceed with import? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Import cancelled."
    exit 0
fi

echo ""
echo "6. Importing data..."
sudo -u postgres psql -d village_bank -f "$SQL_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Import successful!"
    echo ""
    echo "7. Verifying import..."
    NEW_COUNT=$(sudo -u postgres psql -d village_bank -t -c "SELECT COUNT(*) FROM penalty_record;" | xargs)
    echo "   New record count: $NEW_COUNT"
    
    if [ "$NEW_COUNT" -gt "$CURRENT_COUNT" ]; then
        IMPORTED=$((NEW_COUNT - CURRENT_COUNT))
        echo "   ✅ Successfully imported $IMPORTED records"
    else
        echo "   ⚠️  No new records found (may have been duplicates or errors)"
    fi
    
    echo ""
    echo "8. Status breakdown:"
    sudo -u postgres psql -d village_bank -c "SELECT status, COUNT(*) FROM penalty_record GROUP BY status;"
else
    echo ""
    echo "❌ Import failed! Check the error messages above."
    exit 1
fi
