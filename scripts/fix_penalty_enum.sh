#!/bin/bash
# Quick script to fix penalty enum issue on production server
# This restarts the backend to load the updated enum values

echo "=== Fixing Penalty Enum Issue ==="
echo ""

# Check if enum values are correct in code
echo "1. Checking enum values in code..."
if grep -q 'PAID = "paid"' /var/www/luboss-vb/app/models/transaction.py 2>/dev/null; then
    echo "✅ Enum values are correct (lowercase) in code"
else
    echo "❌ Enum values still uppercase in code"
    echo "   Run: git pull origin main"
    exit 1
fi

# Check database enum values
echo ""
echo "2. Checking database enum values..."
DB_ENUMS=$(sudo -u postgres psql -d village_bank -t -c "
SELECT string_agg(enumlabel, ', ' ORDER BY enumsortorder)
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus');
" 2>/dev/null | xargs)

echo "   Database enum values: $DB_ENUMS"

if echo "$DB_ENUMS" | grep -q "paid"; then
    echo "✅ Database has lowercase enum values"
else
    echo "⚠️  Database enum values may be uppercase"
    echo "   This might need a migration fix"
fi

# Clear Python cache (important for enum changes)
echo ""
echo "3. Clearing Python bytecode cache..."
find /var/www/luboss-vb/app -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
find /var/www/luboss-vb/app -name "*.pyc" -delete 2>/dev/null || true
find /var/www/luboss-vb/app -name "*.pyo" -delete 2>/dev/null || true
echo "✅ Python cache cleared"

# Kill all Python processes related to the backend (force reload)
echo ""
echo "4. Stopping backend service and killing any remaining processes..."
sudo systemctl stop luboss-backend
sleep 2

# Kill any remaining uvicorn processes for this app
pkill -f "uvicorn.*app.main:app" 2>/dev/null || true
sleep 1

# Restart backend
echo "5. Starting backend service..."
sudo systemctl start luboss-backend

# Wait for service to fully start
sleep 5

# Check status
echo ""
echo "6. Checking backend status..."
if sudo systemctl is-active --quiet luboss-backend; then
    echo "✅ Backend is running"
else
    echo "❌ Backend failed to start"
    echo "   Check logs: sudo journalctl -u luboss-backend -n 50"
    exit 1
fi

# Check recent logs for errors
echo ""
echo "7. Checking for enum errors in logs..."
RECENT_ERRORS=$(sudo journalctl -u luboss-backend -n 20 --no-pager | grep -i "penaltyrecordstatus\|enum" | tail -3)
if [ -z "$RECENT_ERRORS" ]; then
    echo "✅ No recent enum errors in logs"
else
    echo "⚠️  Recent errors found:"
    echo "$RECENT_ERRORS"
fi

echo ""
echo "=== Fix Complete ==="
echo "The backend has been restarted with the updated enum values."
echo "Try the API call again - it should work now."
