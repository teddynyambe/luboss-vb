# Fix: Port 3000 Not Listening & Nginx Connection Refused

## Problem Identified

From the diagnostic:
- ✅ Services are running
- ❌ Port 3000 NOT listening (but curl works?)
- ❌ Nginx returns 000 (connection refused)
- ⚠️ proxy_pass shows `http://localhost:3000/test` (incorrect)

## Root Cause

The `proxy_pass` in the Nginx config was changed to include `/test` at the end, which is incorrect. When Next.js has `basePath: '/test'`, it expects:
- Requests to come to `/test` (which Nginx handles)
- The proxy should pass the full request URI to Next.js
- But `proxy_pass http://localhost:3000/test;` replaces the URI path

## Solution

### Step 1: Fix the Nginx Config File

The included file `/etc/nginx/sites-available/luboss-vb` has the wrong proxy_pass. Fix it:

```bash
sudo nano /etc/nginx/sites-available/luboss-vb
```

Find this line (around line 23):
```nginx
proxy_pass http://localhost:3000/test;
```

Change it to:
```nginx
proxy_pass http://localhost:3000;
```

**Important:** Remove the `/test` suffix from proxy_pass.

### Step 2: Check Why Port 3000 Isn't Listening

Even though the service is "active", the port might not be bound. Check:

```bash
# Check what's actually listening
sudo ss -tlnp | grep 3000

# Check if Next.js is running but on a different interface
sudo netstat -tlnp | grep 3000

# Check frontend service logs for errors
sudo journalctl -u luboss-frontend -n 50 --no-pager
```

### Step 3: Check Frontend Service Configuration

The service might be configured to listen on a different interface. Check:

```bash
sudo cat /etc/systemd/system/luboss-frontend.service
```

Look for the `ExecStart` line. It should be:
```
ExecStart=/usr/bin/npm run start
```

And check if there's a PORT environment variable that might be wrong.

### Step 4: Restart Services

After fixing the config:

```bash
# Reload Nginx
sudo nginx -t
sudo systemctl reload nginx

# Restart frontend (to ensure it's listening on the right port)
sudo systemctl restart luboss-frontend

# Wait a few seconds, then check
sleep 5
sudo lsof -i:3000
```

### Step 5: Verify

```bash
# Test direct connection
curl -I http://localhost:3000/test

# Test through Nginx
curl -I https://lubossvb.com/test
```

## Alternative: Check if Next.js is Listening on 127.0.0.1 vs 0.0.0.0

Next.js might be listening on `127.0.0.1` instead of `0.0.0.0`. Check:

```bash
# Check what interface it's listening on
sudo ss -tlnp | grep 3000
```

If it shows `127.0.0.1:3000` instead of `0.0.0.0:3000` or `*:3000`, that's fine - Nginx can still connect via localhost.

## Quick Fix Script

Run this to fix the proxy_pass issue:

```bash
# Backup the file
sudo cp /etc/nginx/sites-available/luboss-vb /etc/nginx/sites-available/luboss-vb.backup

# Fix the proxy_pass (remove /test suffix)
sudo sed -i 's|proxy_pass http://localhost:3000/test;|proxy_pass http://localhost:3000;|g' /etc/nginx/sites-available/luboss-vb

# Test and reload
sudo nginx -t && sudo systemctl reload nginx

# Restart frontend
sudo systemctl restart luboss-frontend

# Wait and check
sleep 5
echo "=== Port Check ==="
sudo lsof -i:3000 || echo "Port 3000 still not listening"

echo -e "\n=== Test ==="
curl -I http://localhost:3000/test
curl -I https://lubossvb.com/test
```

## If Port Still Not Listening

If port 3000 still isn't listening after restart:

1. **Check if Next.js build exists:**
   ```bash
   ls -la /var/www/luboss-vb/ui/.next
   ```

2. **Check if npm start is working:**
   ```bash
   cd /var/www/luboss-vb/ui
   sudo -u www-data npm start
   # (Press Ctrl+C after checking if it starts)
   ```

3. **Check environment variables:**
   ```bash
   sudo systemctl show luboss-frontend | grep Environment
   ```

4. **Check if there's a port conflict:**
   ```bash
   sudo lsof -i:3000
   sudo netstat -tlnp | grep 3000
   ```

The key fix is removing `/test` from the proxy_pass URL.
