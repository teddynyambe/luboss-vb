# Fix: Backend Database Connection Errors

## Problem

Backend service is running but showing database connection errors in logs:
```
psycopg2 connection errors
SQLAlchemy connection failures
```

## Diagnostic Steps

### 1. Check Full Error Logs

```bash
# View complete error message
sudo journalctl -u luboss-backend -n 100 --no-pager | grep -A 10 -i error

# Or view all recent logs
sudo journalctl -u luboss-backend -n 100 --no-pager
```

### 2. Check Database Connection String

```bash
# Check if .env file exists
sudo cat /var/www/luboss-vb/app/.env

# OR check .env.production
sudo cat /var/www/luboss-vb/app/.env.production

# Look for DATABASE_URL
sudo grep DATABASE_URL /var/www/luboss-vb/app/.env*
```

**Expected format:**
```
DATABASE_URL=postgresql://username:password@localhost:5432/village_bank
```

### 3. Check if PostgreSQL is Running

```bash
# Check PostgreSQL service
sudo systemctl status postgresql

# Check if PostgreSQL is listening
sudo lsof -i:5432
sudo ss -tlnp | grep 5432
```

### 4. Test Database Connection

```bash
# Test connection from command line
cd /var/www/luboss-vb/app
source venv/bin/activate

# Test with psql
psql $DATABASE_URL -c "SELECT 1;"

# OR test with Python
python -c "
from app.core.config import settings
print('DATABASE_URL:', settings.DATABASE_URL)
from app.db.database import engine
conn = engine.connect()
print('Connection successful!')
conn.close()
"
```

### 5. Check Database Credentials

```bash
# Check if database exists
sudo -u postgres psql -l | grep village_bank

# Check if user exists and has permissions
sudo -u postgres psql -c "\du"

# Test connection as postgres user
sudo -u postgres psql village_bank -c "SELECT 1;"
```

## Common Fixes

### Fix 1: Missing or Incorrect DATABASE_URL

If `.env` file is missing or has wrong DATABASE_URL:

```bash
# Create or edit .env file
sudo nano /var/www/luboss-vb/app/.env
```

Add:
```env
DATABASE_URL=postgresql://username:password@localhost:5432/village_bank
SECRET_KEY=your-secret-key-here
```

Replace:
- `username` with your PostgreSQL username
- `password` with your PostgreSQL password
- `village_bank` with your database name

Then restart backend:
```bash
sudo systemctl restart luboss-backend
```

### Fix 2: PostgreSQL Not Running

```bash
# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Check status
sudo systemctl status postgresql
```

### Fix 3: Database Doesn't Exist

```bash
# Create database
sudo -u postgres createdb village_bank

# Or if using a specific user
sudo -u postgres psql -c "CREATE DATABASE village_bank;"
```

### Fix 4: User Doesn't Have Permissions

```bash
# Grant permissions
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE village_bank TO your_username;"

# Or create user if doesn't exist
sudo -u postgres psql -c "CREATE USER your_username WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE village_bank TO your_username;"
```

### Fix 5: Connection String Format Error

The DATABASE_URL must be in correct format:
```
postgresql://user:password@host:port/database
```

Common mistakes:
- ❌ `postgres://` (old format, use `postgresql://`)
- ❌ Missing password
- ❌ Wrong port (should be 5432)
- ❌ Wrong host (use `localhost` for local connections)

### Fix 6: Environment Variables Not Loaded

The service might not be reading the .env file. Check the service file:

```bash
# Check service file
sudo cat /etc/systemd/system/luboss-backend.service

# Look for EnvironmentFile or Environment directives
```

If missing, you might need to add:
```ini
[Service]
EnvironmentFile=/var/www/luboss-vb/app/.env
```

Or set environment variables directly in the service file.

## Quick Diagnostic Script

```bash
#!/bin/bash
echo "=== 1. Backend Service ==="
sudo systemctl is-active luboss-backend && echo "✅ Running" || echo "❌ Not running"

echo -e "\n=== 2. PostgreSQL Service ==="
sudo systemctl is-active postgresql && echo "✅ Running" || echo "❌ Not running"

echo -e "\n=== 3. PostgreSQL Port ==="
sudo lsof -i:5432 > /dev/null 2>&1 && echo "✅ Listening" || echo "❌ Not listening"

echo -e "\n=== 4. .env File ==="
if [ -f /var/www/luboss-vb/app/.env ]; then
    echo "✅ .env exists"
    if grep -q DATABASE_URL /var/www/luboss-vb/app/.env; then
        echo "✅ DATABASE_URL found"
        # Show first part (without password)
        grep DATABASE_URL /var/www/luboss-vb/app/.env | sed 's/:[^@]*@/:***@/'
    else
        echo "❌ DATABASE_URL NOT found"
    fi
else
    echo "❌ .env file NOT found"
fi

echo -e "\n=== 5. Database Exists ==="
sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw village_bank && echo "✅ Database exists" || echo "❌ Database NOT found"

echo -e "\n=== 6. Recent Backend Errors ==="
sudo journalctl -u luboss-backend -n 5 --no-pager | grep -i error | tail -3
```

Save as `check_db.sh`, make executable, and run:
```bash
chmod +x check_db.sh
./check_db.sh
```

## After Fixing

1. **Restart backend:**
   ```bash
   sudo systemctl restart luboss-backend
   ```

2. **Check logs:**
   ```bash
   sudo journalctl -u luboss-backend -f
   ```

3. **Test API:**
   ```bash
   curl http://localhost:8002/health
   curl https://lubossvb.com/test/api/health
   ```

## Most Common Issue

The most common issue is **missing or incorrect DATABASE_URL** in the `.env` file. Make sure:
1. File exists: `/var/www/luboss-vb/app/.env`
2. Contains: `DATABASE_URL=postgresql://user:pass@localhost:5432/village_bank`
3. Format is correct (no spaces, correct syntax)
4. Credentials are correct
