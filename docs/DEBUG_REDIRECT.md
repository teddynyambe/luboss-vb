# Debug: Still Redirecting to /login

## Step-by-Step Debugging

### 1. Verify Nginx Include is Active

```bash
# Check if include is in the config
sudo grep -A 5 "include.*luboss-vb" /etc/nginx/sites-available/lubossvb.conf

# Check if Nginx sees the location blocks
sudo nginx -T | grep -A 10 "location /test"
```

**Expected:** You should see the `/test` location block in the output.

### 2. Check if Services are Running

```bash
# Check frontend service
sudo systemctl status luboss-frontend

# Check backend service  
sudo systemctl status luboss-backend

# If not running, start them:
sudo systemctl start luboss-frontend
sudo systemctl start luboss-backend
```

### 3. Check if Ports are Listening

```bash
# Check port 3000 (frontend)
sudo lsof -i:3000
# OR
sudo netstat -tlnp | grep 3000

# Check port 8002 (backend)
sudo lsof -i:8002
# OR
sudo netstat -tlnp | grep 8002
```

**Expected:** Both ports should show processes listening.

### 4. Test Direct Connection to Services

```bash
# Test frontend directly (from server)
curl -I http://localhost:3000/test

# Test backend directly
curl http://localhost:8002/health
```

**Expected:** 
- Frontend should return 200 OK
- Backend should return `{"status":"ok"}`

### 5. Check Nginx Error Logs

```bash
# Watch error log in real-time
sudo tail -f /var/log/nginx/lubossvb.com_error.log

# Then in another terminal, try accessing /test
curl -I https://lubossvb.com/test
```

Look for any errors in the log.

### 6. Check Nginx Access Logs

```bash
# Check recent access logs
sudo tail -20 /var/log/nginx/lubossvb.com_access.log | grep /test
```

### 7. Verify Location Block Order

The issue might be that `/` location is catching `/test` first. Check the order:

```bash
sudo nginx -T | grep -B 2 -A 10 "location /"
sudo nginx -T | grep -B 2 -A 10 "location /test"
```

**Important:** `/test` location should be processed, but if `/` comes first and matches, it might catch it. However, Nginx should match the most specific path first.

### 8. Test with curl (Detailed)

```bash
# Test with verbose output
curl -v https://lubossvb.com/test 2>&1 | head -30

# Check what status code you get
curl -I https://lubossvb.com/test
```

### 9. Check if Next.js is Built with Correct basePath

```bash
# SSH into server
ssh teddy@luboss95vb.com

# Check environment variables
cat /var/www/luboss-vb/ui/.env.production
# OR
cat /var/www/luboss-vb/ui/.env

# Check if basePath is set in next.config
cat /var/www/luboss-vb/ui/next.config.ts
```

**Expected:** Should show `NEXT_PUBLIC_BASE_PATH=/test`

### 10. Check if Frontend Service is Actually Serving

```bash
# Check service logs
sudo journalctl -u luboss-frontend -n 50

# Check if it's listening on the right port
sudo ss -tlnp | grep 3000
```

## Common Issues and Fixes

### Issue 1: Services Not Running

**Fix:**
```bash
sudo systemctl start luboss-frontend
sudo systemctl start luboss-backend
sudo systemctl enable luboss-frontend
sudo systemctl enable luboss-backend
```

### Issue 2: Next.js Not Built with basePath

**Fix:**
```bash
cd /var/www/luboss-vb/ui
NEXT_PUBLIC_BASE_PATH=/test npm run build
sudo systemctl restart luboss-frontend
```

### Issue 3: Location Block Order Issue

If `/` is catching `/test`, we need to make `/test` more specific. The included file should handle this, but let's verify.

**Check:**
```bash
sudo nginx -T | grep -E "location /|location /test" -A 5
```

### Issue 4: Proxy Pass Not Working

The proxy might not be forwarding correctly. Check the proxy_pass configuration:

```bash
sudo cat /etc/nginx/sites-available/luboss-vb | grep -A 5 "location /test"
```

Should show:
```nginx
location /test {
    proxy_pass http://localhost:3000;
    ...
}
```

### Issue 5: Next.js Client-Side Redirect

If Next.js is doing client-side redirects, we need to check the router configuration. The app might be redirecting `/test` to `/login` on the client side.

**Check browser console:**
1. Open browser DevTools (F12)
2. Go to Network tab
3. Visit `https://lubossvb.com/test`
4. Check what requests are made
5. Check Console tab for errors

## Quick Diagnostic Script

Run this on your server:

```bash
#!/bin/bash
echo "=== Nginx Config ==="
sudo nginx -t 2>&1
echo ""

echo "=== Include Check ==="
sudo grep -q "include.*luboss-vb" /etc/nginx/sites-available/lubossvb.conf && echo "✅ Include found" || echo "❌ Include NOT found"

echo ""
echo "=== Location /test ==="
sudo nginx -T 2>/dev/null | grep -A 10 "location /test" | head -15

echo ""
echo "=== Services ==="
sudo systemctl is-active luboss-frontend && echo "✅ Frontend running" || echo "❌ Frontend NOT running"
sudo systemctl is-active luboss-backend && echo "✅ Backend running" || echo "❌ Backend NOT running"

echo ""
echo "=== Ports ==="
sudo lsof -i:3000 > /dev/null && echo "✅ Port 3000 listening" || echo "❌ Port 3000 NOT listening"
sudo lsof -i:8002 > /dev/null && echo "✅ Port 8002 listening" || echo "❌ Port 8002 NOT listening"

echo ""
echo "=== Direct Test ==="
curl -s http://localhost:3000/test | head -5
echo ""

echo "=== Nginx Test ==="
curl -I https://lubossvb.com/test 2>&1 | head -10
```

Save as `debug_redirect.sh`, make executable, and run:
```bash
chmod +x debug_redirect.sh
./debug_redirect.sh
```

## Most Likely Issues

1. **Services not running** - Most common
2. **Next.js not built with basePath** - Check build
3. **Location block not matching** - Check Nginx config
4. **Client-side redirect in Next.js** - Check browser console
