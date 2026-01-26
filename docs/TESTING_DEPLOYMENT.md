# Testing the Deployment

This guide shows you how to verify that your deployed application is running correctly.

## Quick Test Checklist

1. ✅ Check systemd services are running
2. ✅ Check ports are listening
3. ✅ Test backend API endpoint
4. ✅ Test frontend in browser
5. ✅ Check logs for errors

## 1. Check Systemd Services

SSH into your server and check if the services are running:

```bash
# SSH into server
ssh teddy@luboss95vb.com

# Check backend service status
sudo systemctl status luboss-backend

# Check frontend service status
sudo systemctl status luboss-frontend

# Or check both at once
sudo systemctl status luboss-backend luboss-frontend
```

**Expected output:**
- Status should show `active (running)`
- Should show "Main PID" and uptime

**If services are not running:**
```bash
# Start them manually
sudo systemctl start luboss-backend
sudo systemctl start luboss-frontend

# Enable them to start on boot
sudo systemctl enable luboss-backend
sudo systemctl enable luboss-frontend
```

## 2. Check Ports are Listening

Verify that the backend and frontend are listening on the correct ports:

```bash
# Check backend port (8002)
sudo lsof -i:8002
# OR
sudo netstat -tlnp | grep 8002
# OR
ss -tlnp | grep 8002

# Check frontend port (3000)
sudo lsof -i:3000
# OR
sudo netstat -tlnp | grep 3000
# OR
ss -tlnp | grep 3000
```

**Expected output:**
- Port 8002: Should show Python/FastAPI process
- Port 3000: Should show Node.js/Next.js process

## 3. Test Backend API

Test the backend API directly:

```bash
# From your local machine or server
# Test health endpoint
curl http://lubossvb.com/test/api/health

# Test with HTTPS (if SSL is configured)
curl https://lubossvb.com/test/api/health

# Test from server itself
curl http://localhost:8002/health
```

**Expected response:**
```json
{"status":"ok"}
```

**If you get connection refused:**
- Check if backend service is running
- Check if port 8002 is listening
- Check backend logs (see section 5)

## 4. Test Frontend in Browser

Open your web browser and navigate to:

```
https://lubossvb.com/test
```

**Or if testing locally on server:**
```
http://localhost:3000
```

**What to check:**
- ✅ Page loads without errors
- ✅ No 404 errors
- ✅ CSS and JavaScript load correctly
- ✅ Can navigate to login page
- ✅ API calls work (check browser console for errors)

**Common issues:**
- **404 Not Found**: Check Nginx configuration, verify `/test` location block exists
- **502 Bad Gateway**: Backend not running or not accessible
- **503 Service Unavailable**: Frontend not running
- **SSL errors**: Check SSL certificate configuration

## 5. Check Logs

If something isn't working, check the logs:

### Backend Logs

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

### Frontend Logs

```bash
# View recent logs
sudo journalctl -u luboss-frontend -n 50

# Follow logs in real-time
sudo journalctl -u luboss-frontend -f

# View logs since last boot
sudo journalctl -u luboss-frontend -b
```

### Nginx Logs

```bash
# Access logs
sudo tail -f /var/log/nginx/access.log

# Error logs
sudo tail -f /var/log/nginx/error.log

# Filter for /test path
sudo tail -f /var/log/nginx/access.log | grep /test
sudo tail -f /var/log/nginx/error.log | grep /test
```

## 6. Test Full Application Flow

1. **Access the application:**
   ```
   https://lubossvb.com/test
   ```

2. **Test login:**
   - Navigate to login page
   - Try logging in with test credentials
   - Check browser console (F12) for API errors

3. **Test API endpoints:**
   ```bash
   # Get auth token (replace with actual credentials)
   curl -X POST https://lubossvb.com/test/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"testpass"}'
   
   # Use token to access protected endpoint
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://lubossvb.com/test/api/member/dashboard
   ```

## 7. Verify Nginx Configuration

Check that Nginx is correctly configured:

```bash
# Test Nginx configuration
sudo nginx -t

# Reload Nginx if config changed
sudo systemctl reload nginx

# Check Nginx status
sudo systemctl status nginx

# Verify /test location is configured
sudo grep -r "location /test" /etc/nginx/
```

## 8. Quick Health Check Script

Create a simple script to check everything at once:

```bash
#!/bin/bash
# save as check_deployment.sh

echo "=== Service Status ==="
sudo systemctl is-active luboss-backend && echo "✅ Backend: Running" || echo "❌ Backend: Not running"
sudo systemctl is-active luboss-frontend && echo "✅ Frontend: Running" || echo "❌ Frontend: Not running"

echo -e "\n=== Port Status ==="
sudo lsof -i:8002 > /dev/null && echo "✅ Port 8002: Listening" || echo "❌ Port 8002: Not listening"
sudo lsof -i:3000 > /dev/null && echo "✅ Port 3000: Listening" || echo "❌ Port 3000: Not listening"

echo -e "\n=== API Health ==="
curl -s http://localhost:8002/health > /dev/null && echo "✅ Backend API: Responding" || echo "❌ Backend API: Not responding"

echo -e "\n=== Nginx Status ==="
sudo systemctl is-active nginx && echo "✅ Nginx: Running" || echo "❌ Nginx: Not running"
sudo nginx -t 2>&1 | grep -q "successful" && echo "✅ Nginx Config: Valid" || echo "❌ Nginx Config: Invalid"
```

Make it executable and run:
```bash
chmod +x check_deployment.sh
./check_deployment.sh
```

## Troubleshooting

### Service won't start

```bash
# Check service logs for errors
sudo journalctl -u luboss-backend -n 100
sudo journalctl -u luboss-frontend -n 100

# Check if ports are already in use
sudo lsof -i:8002
sudo lsof -i:3000

# Check if environment variables are set
sudo cat /var/www/luboss-vb/app/.env
```

### Port already in use

```bash
# Find what's using the port
sudo lsof -i:8002
sudo lsof -i:3000

# Kill the process (replace PID with actual process ID)
sudo kill -9 PID
```

### Database connection errors

```bash
# Check database is running
sudo systemctl status postgresql

# Test database connection from server
psql -h localhost -U your_user -d village_bank -c "SELECT 1;"

# Check database URL in .env
sudo cat /var/www/luboss-vb/app/.env | grep DATABASE_URL
```

### Frontend build errors

```bash
# Check if build completed
ls -la /var/www/luboss-vb/ui/.next

# Rebuild manually
cd /var/www/luboss-vb/ui
NEXT_PUBLIC_BASE_PATH=/test npm run build
```

## Success Indicators

Your deployment is successful when:

✅ Both services show `active (running)`  
✅ Ports 8002 and 3000 are listening  
✅ `curl http://localhost:8002/health` returns `{"status":"ok"}`  
✅ `https://lubossvb.com/test` loads in browser  
✅ No errors in browser console  
✅ Can log in and navigate the application  
✅ API calls return expected data  

## Next Steps

Once everything is working:
1. Test all major features
2. Monitor logs for any warnings
3. Set up monitoring/alerting (optional)
4. Document any custom configurations
5. Create backups of working configuration
