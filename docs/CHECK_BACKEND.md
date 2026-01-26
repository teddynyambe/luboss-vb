# How to Check if Backend is Running

## Quick Checks

### 1. Check Service Status

```bash
# Check if backend service is running
sudo systemctl status luboss-backend

# Check if it's active
sudo systemctl is-active luboss-backend
```

**Expected:** Should show `active (running)`

### 2. Check if Port 8002 is Listening

```bash
# Method 1: Using lsof
sudo lsof -i:8002

# Method 2: Using ss
sudo ss -tlnp | grep 8002

# Method 3: Using netstat
sudo netstat -tlnp | grep 8002
```

**Expected:** Should show a Python/uvicorn process listening on port 8002

### 3. Test Backend Health Endpoint

```bash
# Test directly (from server)
curl http://localhost:8002/health

# Test through Nginx
curl https://lubossvb.com/test/api/health

# Test with verbose output
curl -v http://localhost:8002/health
```

**Expected:** Should return `{"status":"ok"}`

### 4. Check Backend Logs

```bash
# View recent logs
sudo journalctl -u luboss-backend -n 50

# Follow logs in real-time
sudo journalctl -u luboss-backend -f

# View logs since last boot
sudo journalctl -u luboss-backend -b

# View logs from today
sudo journalctl -u luboss-backend --since today
```

### 5. Check if Process is Running

```bash
# Find the backend process
ps aux | grep uvicorn
ps aux | grep luboss-backend

# Check process details
sudo systemctl show luboss-backend | grep -E "MainPID|ExecStart|WorkingDirectory"
```

## Troubleshooting

### Backend Not Running

If the service is not running:

```bash
# Start the service
sudo systemctl start luboss-backend

# Enable it to start on boot
sudo systemctl enable luboss-backend

# Check status
sudo systemctl status luboss-backend
```

### Port Not Listening

If port 8002 is not listening:

```bash
# Check if something else is using the port
sudo lsof -i:8002

# Check backend logs for errors
sudo journalctl -u luboss-backend -n 100

# Check if environment variables are set
sudo cat /var/www/luboss-vb/app/.env
```

### Backend Returns 500 Error

If backend is running but returns 500:

1. **Check logs for errors:**
   ```bash
   sudo journalctl -u luboss-backend -n 100 | grep -i error
   ```

2. **Check database connection:**
   ```bash
   # Test database connection
   sudo -u www-data /var/www/luboss-vb/app/venv/bin/python -c "
   from app.core.config import settings
   print(settings.DATABASE_URL)
   "
   ```

3. **Check environment variables:**
   ```bash
   sudo cat /var/www/luboss-vb/app/.env
   # Should have DATABASE_URL and SECRET_KEY
   ```

4. **Test database connection:**
   ```bash
   # From the app directory
   cd /var/www/luboss-vb/app
   source venv/bin/activate
   python -c "from app.db.database import engine; engine.connect()"
   ```

## Quick Diagnostic Script

Run this to check everything at once:

```bash
#!/bin/bash
echo "=== Backend Service Status ==="
sudo systemctl is-active luboss-backend && echo "✅ Service is running" || echo "❌ Service is NOT running"

echo -e "\n=== Port 8002 ==="
sudo lsof -i:8002 > /dev/null 2>&1 && echo "✅ Port 8002 is listening" || echo "❌ Port 8002 is NOT listening"

echo -e "\n=== Health Check (Direct) ==="
curl -s http://localhost:8002/health && echo "" || echo "❌ Cannot connect to backend"

echo -e "\n=== Health Check (via Nginx) ==="
curl -s https://lubossvb.com/test/api/health && echo "" || echo "❌ Cannot connect via Nginx"

echo -e "\n=== Recent Logs (last 3 lines) ==="
sudo journalctl -u luboss-backend -n 3 --no-pager
```

Save as `check_backend.sh`, make executable, and run:
```bash
chmod +x check_backend.sh
./check_backend.sh
```

## Common Issues

### Issue: Service shows as active but port not listening

**Cause:** Service might have crashed after starting, or there's a configuration error.

**Fix:**
```bash
# Check logs
sudo journalctl -u luboss-backend -n 50

# Restart service
sudo systemctl restart luboss-backend

# Check again
sudo systemctl status luboss-backend
```

### Issue: 500 Internal Server Error

**Cause:** Usually a database connection issue, missing environment variables, or application error.

**Fix:**
1. Check logs: `sudo journalctl -u luboss-backend -n 100`
2. Verify `.env` file exists and has correct values
3. Test database connection
4. Check if migrations are up to date

### Issue: Connection Refused

**Cause:** Backend not running or firewall blocking.

**Fix:**
1. Start service: `sudo systemctl start luboss-backend`
2. Check firewall: `sudo ufw status` or `sudo iptables -L`
