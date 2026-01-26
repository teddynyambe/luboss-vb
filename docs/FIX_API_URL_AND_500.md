# Fix: Double /api/api and 500 Error

## Issue 1: Double /api/api in URL

The URL shows: `https://luboss95vb.com/test/api/api/auth/login`

This means `NEXT_PUBLIC_API_URL` is set to `https://luboss95vb.com/test/api` but it should be `https://luboss95vb.com/test` (without `/api`).

## Fix API URL

### Step 1: Update Frontend Service File

```bash
# Edit the service file
sudo nano /etc/systemd/system/luboss-frontend.service
```

Find the line with `NEXT_PUBLIC_API_URL` and change it from:
```
Environment="NEXT_PUBLIC_API_URL=https://luboss95vb.com/test/api"
```

To:
```
Environment="NEXT_PUBLIC_API_URL=https://luboss95vb.com/test"
```

### Step 2: Reload and Restart

```bash
sudo systemctl daemon-reload
sudo systemctl restart luboss-frontend
```

### Quick Fix Command

```bash
# Fix the API URL
sudo sed -i 's|NEXT_PUBLIC_API_URL=https://luboss95vb.com/test/api|NEXT_PUBLIC_API_URL=https://luboss95vb.com/test|g' /etc/systemd/system/luboss-frontend.service

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart luboss-frontend

# Verify
sudo systemctl show luboss-frontend | grep NEXT_PUBLIC_API_URL
```

## Issue 2: Backend 500 Error

The backend is running but returning 500. Check the actual error:

### Step 1: Check Backend Logs for Error

```bash
# View recent error logs
sudo journalctl -u luboss-backend -n 100 --no-pager | grep -i error

# Or view all recent logs
sudo journalctl -u luboss-backend -n 100 --no-pager

# Follow logs in real-time
sudo journalctl -u luboss-backend -f
```

### Step 2: Test Backend Directly

```bash
# Test health endpoint
curl http://localhost:8002/health

# Test login endpoint directly
curl -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'

# Check response
curl -v http://localhost:8002/api/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"test","password":"test"}' 2>&1
```

### Step 3: Check Database Connection

```bash
# Test database connection
cd /var/www/luboss-vb/app
source venv/bin/activate
python -c "
from app.core.config import settings
print('DATABASE_URL:', settings.DATABASE_URL)
from app.db.database import engine
try:
    conn = engine.connect()
    print('✅ Database connection successful!')
    conn.close()
except Exception as e:
    print('❌ Database connection failed:', e)
"
```

### Step 4: Check if Migrations Are Applied

```bash
cd /var/www/luboss-vb/app
source venv/bin/activate

# Check current migration version
alembic current

# Check for pending migrations
alembic heads

# Apply migrations if needed
alembic upgrade head
```

## Common 500 Error Causes

### 1. Database Connection Issues

**Symptoms:** Connection errors in logs

**Fix:**
- Verify `.env` file has correct `DATABASE_URL`
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Test connection manually

### 2. Missing Environment Variables

**Symptoms:** Validation errors for Settings

**Fix:**
- Ensure `.env` file has `DATABASE_URL` and `SECRET_KEY`
- Check service file loads `.env`: `EnvironmentFile=/var/www/luboss-vb/app/.env`

### 3. Database Schema Not Created

**Symptoms:** Table not found errors

**Fix:**
```bash
cd /var/www/luboss-vb/app
source venv/bin/activate
alembic upgrade head
```

### 4. Import Errors

**Symptoms:** Module not found errors

**Fix:**
- Check virtual environment is correct
- Reinstall dependencies: `pip install -r requirements.txt`

## Complete Diagnostic Script

```bash
#!/bin/bash
echo "=== 1. Frontend API URL ==="
sudo systemctl show luboss-frontend | grep NEXT_PUBLIC_API_URL

echo -e "\n=== 2. Backend Status ==="
sudo systemctl is-active luboss-backend && echo "✅ Running" || echo "❌ Not running"

echo -e "\n=== 3. Backend Health ==="
curl -s http://localhost:8002/health && echo "" || echo "❌ Health check failed"

echo -e "\n=== 4. Database Connection ==="
cd /var/www/luboss-vb/app
source venv/bin/activate
python -c "
from app.core.config import settings
from app.db.database import engine
try:
    conn = engine.connect()
    print('✅ Database connection OK')
    conn.close()
except Exception as e:
    print('❌ Database error:', str(e)[:100])
" 2>&1

echo -e "\n=== 5. Recent Backend Errors ==="
sudo journalctl -u luboss-backend -n 20 --no-pager | grep -i -E "error|exception|traceback" | tail -5

echo -e "\n=== 6. Test Login Endpoint ==="
curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test","password":"test"}' | head -c 200
echo ""
```

Save as `diagnose_500.sh`, make executable, and run:
```bash
chmod +x diagnose_500.sh
./diagnose_500.sh
```

## Quick Fix Summary

1. **Fix API URL:**
   ```bash
   sudo sed -i 's|NEXT_PUBLIC_API_URL=https://luboss95vb.com/test/api|NEXT_PUBLIC_API_URL=https://luboss95vb.com/test|g' /etc/systemd/system/luboss-frontend.service
   sudo systemctl daemon-reload
   sudo systemctl restart luboss-frontend
   ```

2. **Check Backend Error:**
   ```bash
   sudo journalctl -u luboss-backend -n 100 --no-pager | tail -30
   ```

3. **Test Backend:**
   ```bash
   curl -v http://localhost:8002/api/auth/login -X POST \
     -H "Content-Type: application/json" \
     -d '{"email":"test","password":"test"}'
   ```

Share the backend error logs so we can identify the specific issue causing the 500 error.
