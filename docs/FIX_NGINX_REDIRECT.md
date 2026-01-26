# Fix: /test Redirecting to /login

## Problem

When accessing `https://luboss95vb.com/test`, it redirects to `https://luboss95vb.com/login` (the default production server) instead of serving the new Next.js app.

## Root Cause

The Nginx include directive hasn't been added to the main server block yet. This means:
- Requests to `/test` don't match any location block
- They fall through to the default `/` location
- The old production app handles the request and redirects to `/login`

## Solution

### Step 1: Verify the Include File Exists

SSH into your server and check:

```bash
ssh teddy@luboss95vb.com
sudo ls -la /etc/nginx/sites-available/luboss-vb
```

You should see the file exists. If not, the deployment didn't complete properly.

### Step 2: Find Your Main Nginx Config

```bash
# List all available sites
sudo ls -la /etc/nginx/sites-available/

# Check which site is enabled (usually lubossvb.com or default)
sudo ls -la /etc/nginx/sites-enabled/
```

The main config is likely one of:
- `/etc/nginx/sites-available/lubossvb.com`
- `/etc/nginx/sites-available/default`
- `/etc/nginx/sites-available/luboss95vb.com`

### Step 3: Edit the Main Config

```bash
# Edit the main config (replace with your actual file)
sudo nano /etc/nginx/sites-available/lubossvb.com
```

### Step 4: Add the Include Directive

Find the `server { }` block and add the include line **inside** it, **after** existing location blocks:

```nginx
server {
    listen 443 ssl;
    server_name lubossvb.com www.lubossvb.com;
    
    ssl_certificate /etc/ssl/luboss/certificate.crt;
    ssl_certificate_key /etc/ssl/luboss/private.key;
    
    # Existing production locations
    location /api {
        # ... existing config ...
    }
    
    location / {
        # ... existing config for production frontend ...
    }
    
    # ⬇️ ADD THIS LINE HERE (inside the server block, after location blocks):
    include /etc/nginx/sites-available/luboss-vb;
}
```

**Important:** The include must be **inside** the `server { }` block, not outside.

### Step 5: Test and Reload Nginx

```bash
# Test the configuration
sudo nginx -t

# If test passes, reload Nginx
sudo systemctl reload nginx
```

### Step 6: Verify It Works

1. **Check Nginx is running:**
   ```bash
   sudo systemctl status nginx
   ```

2. **Test the /test endpoint:**
   ```bash
   curl -I https://luboss95vb.com/test
   ```
   
   You should get a response from the Next.js app (port 3000), not a redirect.

3. **Check in browser:**
   - Go to `https://luboss95vb.com/test`
   - It should show the Next.js app, not redirect to `/login`
   - The URL should stay as `/test` (or `/test/login` if not logged in)

## Troubleshooting

### If nginx -t fails:

Check the error message. Common issues:

1. **"location directive is not allowed here"**
   - The include is outside the server block
   - Move it inside the `server { }` block

2. **"file not found"**
   - The include path is wrong
   - Verify: `sudo ls -la /etc/nginx/sites-available/luboss-vb`

3. **Syntax errors in included file**
   - Check the included file: `sudo nginx -T | grep -A 50 "location /test"`

### If it still redirects:

1. **Check if services are running:**
   ```bash
   sudo systemctl status luboss-frontend
   sudo systemctl status luboss-backend
   ```

2. **Check if ports are listening:**
   ```bash
   sudo lsof -i:3000  # Frontend
   sudo lsof -i:8002  # Backend
   ```

3. **Check Nginx error logs:**
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```

4. **Verify the location block is active:**
   ```bash
   sudo nginx -T | grep -A 20 "location /test"
   ```

### If Next.js redirects to /login (without /test prefix):

This means Next.js router isn't respecting basePath. Check:

1. **Verify basePath is set in build:**
   ```bash
   ssh teddy@luboss95vb.com
   cat /var/www/luboss-vb/ui/.env.production
   # Should show: NEXT_PUBLIC_BASE_PATH=/test
   ```

2. **Rebuild if needed:**
   ```bash
   cd /var/www/luboss-vb/ui
   NEXT_PUBLIC_BASE_PATH=/test npm run build
   sudo systemctl restart luboss-frontend
   ```

## Expected Behavior After Fix

- `https://luboss95vb.com/test` → Shows Next.js app
- `https://luboss95vb.com/test/login` → Login page (within /test)
- `https://luboss95vb.com/test/api/health` → Backend API
- `https://luboss95vb.com/` → Old production app (unchanged)
- `https://luboss95vb.com/login` → Old production login (unchanged)

## Quick Verification Script

Run this on your server to verify everything:

```bash
#!/bin/bash
echo "=== Nginx Config Test ==="
sudo nginx -t

echo -e "\n=== Include File Exists ==="
sudo test -f /etc/nginx/sites-available/luboss-vb && echo "✅ File exists" || echo "❌ File missing"

echo -e "\n=== Include in Main Config ==="
sudo grep -q "include.*luboss-vb" /etc/nginx/sites-available/*.conf && echo "✅ Include found" || echo "❌ Include not found"

echo -e "\n=== Services Running ==="
sudo systemctl is-active luboss-frontend && echo "✅ Frontend running" || echo "❌ Frontend not running"
sudo systemctl is-active luboss-backend && echo "✅ Backend running" || echo "❌ Backend not running"

echo -e "\n=== Ports Listening ==="
sudo lsof -i:3000 > /dev/null && echo "✅ Port 3000 listening" || echo "❌ Port 3000 not listening"
sudo lsof -i:8002 > /dev/null && echo "✅ Port 8002 listening" || echo "❌ Port 8002 not listening"
```

Save as `check_nginx.sh`, make executable, and run:
```bash
chmod +x check_nginx.sh
./check_nginx.sh
```
