# Fix: PostgreSQL Connection Error

## Error

```
connection to server at "localhost" (::1), port 5432 failed: FATAL
```

The backend cannot connect to PostgreSQL.

## Diagnostic Steps

### 1. Check if PostgreSQL is Running

```bash
# Check PostgreSQL service status
sudo systemctl status postgresql

# Check if it's listening on port 5432
sudo lsof -i:5432
sudo ss -tlnp | grep 5432
```

### 2. Check DATABASE_URL Configuration

```bash
# Check the .env file
sudo cat /var/www/luboss-vb/app/.env | grep DATABASE_URL

# Check if service is loading the .env file
sudo systemctl show luboss-backend | grep EnvironmentFile
```

### 3. Test Database Connection Manually

```bash
# Test with psql
psql -h localhost -U your_username -d village_bank -c "SELECT 1;"

# Or test with the connection string from .env
source /var/www/luboss-vb/app/.env
psql $DATABASE_URL -c "SELECT 1;"
```

## Common Fixes

### Fix 1: PostgreSQL Not Running

```bash
# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Check status
sudo systemctl status postgresql
```

### Fix 2: Wrong DATABASE_URL Format

The DATABASE_URL must be in correct format:
```
postgresql://username:password@host:port/database
```

Check your .env file:
```bash
sudo nano /var/www/luboss-vb/app/.env
```

Make sure it has:
```env
DATABASE_URL=postgresql://username:password@localhost:5432/village_bank
```

**Common mistakes:**
- ❌ Using `postgres://` instead of `postgresql://`
- ❌ Missing password
- ❌ Wrong username
- ❌ Wrong database name
- ❌ Using `127.0.0.1` instead of `localhost` (sometimes causes IPv6 issues)

### Fix 3: PostgreSQL Not Listening on IPv6

The error shows it's trying `::1` (IPv6 localhost). If PostgreSQL only listens on IPv4:

**Option A:** Use `127.0.0.1` instead of `localhost`:
```env
DATABASE_URL=postgresql://username:password@127.0.0.1:5432/village_bank
```

**Option B:** Configure PostgreSQL to listen on IPv6 (more complex)

### Fix 4: Authentication Failed

If the username/password is wrong:

```bash
# Check if user exists
sudo -u postgres psql -c "\du"

# Reset password
sudo -u postgres psql -c "ALTER USER your_username WITH PASSWORD 'new_password';"

# Update .env file with new password
sudo nano /var/www/luboss-vb/app/.env
```

### Fix 5: Database Doesn't Exist

```bash
# Check if database exists
sudo -u postgres psql -l | grep village_bank

# Create database if missing
sudo -u postgres createdb village_bank

# Or create with specific owner
sudo -u postgres psql -c "CREATE DATABASE village_bank OWNER your_username;"
```

### Fix 6: Service Not Loading .env File

If the service file doesn't have `EnvironmentFile`:

```bash
# Check service file
sudo cat /etc/systemd/system/luboss-backend.service | grep EnvironmentFile

# If missing, add it
sudo nano /etc/systemd/system/luboss-backend.service
```

Add this line in `[Service]` section:
```ini
EnvironmentFile=/var/www/luboss-vb/app/.env
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart luboss-backend
```

## Quick Fix Script

```bash
#!/bin/bash
echo "=== 1. PostgreSQL Status ==="
sudo systemctl is-active postgresql && echo "✅ Running" || echo "❌ Not running"

echo -e "\n=== 2. PostgreSQL Port ==="
sudo lsof -i:5432 > /dev/null 2>&1 && echo "✅ Listening" || echo "❌ Not listening"

echo -e "\n=== 3. DATABASE_URL Check ==="
if [ -f /var/www/luboss-vb/app/.env ]; then
    if grep -q DATABASE_URL /var/www/luboss-vb/app/.env; then
        echo "✅ DATABASE_URL found"
        # Show without password
        grep DATABASE_URL /var/www/luboss-vb/app/.env | sed 's/:[^@]*@/:***@/'
    else
        echo "❌ DATABASE_URL NOT found"
    fi
else
    echo "❌ .env file NOT found"
fi

echo -e "\n=== 4. EnvironmentFile in Service ==="
sudo grep -q EnvironmentFile /etc/systemd/system/luboss-backend.service && echo "✅ EnvironmentFile configured" || echo "❌ EnvironmentFile missing"

echo -e "\n=== 5. Test Database Connection ==="
if [ -f /var/www/luboss-vb/app/.env ]; then
    source /var/www/luboss-vb/app/.env
    if psql "$DATABASE_URL" -c "SELECT 1;" > /dev/null 2>&1; then
        echo "✅ Connection successful"
    else
        echo "❌ Connection failed"
        echo "Testing with psql..."
        psql "$DATABASE_URL" -c "SELECT 1;" 2>&1 | head -3
    fi
fi

echo -e "\n=== 6. Database Exists ==="
sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw village_bank && echo "✅ Database exists" || echo "❌ Database NOT found"
```

Save as `check_postgres.sh`, make executable, and run:
```bash
chmod +x check_postgres.sh
./check_postgres.sh
```

## Most Common Fix

The most common issue is **using `localhost` when PostgreSQL only listens on IPv4**. Try changing to `127.0.0.1`:

```bash
# Edit .env file
sudo nano /var/www/luboss-vb/app/.env

# Change localhost to 127.0.0.1
# From: postgresql://user:pass@localhost:5432/village_bank
# To:   postgresql://user:pass@127.0.0.1:5432/village_bank

# Restart backend
sudo systemctl restart luboss-backend

# Check logs
sudo journalctl -u luboss-backend -n 20 --no-pager
```

## After Fixing

1. **Restart backend:**
   ```bash
   sudo systemctl restart luboss-backend
   ```

2. **Check logs:**
   ```bash
   sudo journalctl -u luboss-backend -n 20 --no-pager
   ```

3. **Test API:**
   ```bash
   curl http://localhost:8002/health
   curl http://localhost:8002/api/auth/login -X POST \
     -H "Content-Type: application/json" \
     -d '{"email":"test","password":"test"}'
   ```
