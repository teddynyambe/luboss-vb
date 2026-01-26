# Verifying Deployment After Update

After deploying updates, use these steps to verify everything is working correctly.

## Quick Verification

### 1. Check Service Status

```bash
# SSH to server
ssh teddy@luboss95vb.com

# Check backend service
sudo systemctl status luboss-backend

# Check frontend service
sudo systemctl status luboss-frontend
```

Both should show `Active: active (running)`.

### 2. Check Service Logs

```bash
# Backend logs (last 50 lines)
sudo journalctl -u luboss-backend -n 50 --no-pager

# Frontend logs (last 50 lines)
sudo journalctl -u luboss-frontend -n 50 --no-pager
```

Look for:
- ✅ No error messages
- ✅ "Application startup complete" (backend)
- ✅ "Ready on http://localhost:3000" (frontend)

### 3. Test API Endpoints

```bash
# Health check
curl https://luboss95vb.com/test/api/health

# Should return: {"status":"ok"} or similar
```

### 4. Test Frontend

Open in browser:
- https://luboss95vb.com/test

Should load without errors.

## Detailed Verification

### Check Backend API

```bash
# Test login endpoint (should return 401, not 500)
curl -X POST https://luboss95vb.com/test/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrong"}'

# Should return 401 Unauthorized (not 500 Internal Server Error)
```

### Check Frontend Build

```bash
# On server
cd /var/www/luboss-vb/ui
ls -lh .next

# Should show recent build files
```

### Check Database Connection

```bash
# On server
cd /var/www/luboss-vb
source app/venv/bin/activate

# Test database connection
python -c "
from app.db.base import SessionLocal
db = SessionLocal()
try:
    db.execute('SELECT 1')
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
finally:
    db.close()
"
```

### Check Enum Values (After PenaltyRecordStatus Fix)

```bash
# On server
cd /var/www/luboss-vb
source app/venv/bin/activate

# Run diagnostic script
python scripts/check_penalty_enum.py
```

Should show:
- ✅ Enum values: `['pending', 'approved', 'paid']`
- ✅ Table exists
- ✅ No invalid enum values

## Common Issues After Update

### Issue: Frontend Shows Old Version

**Solution:**
```bash
# Rebuild frontend
cd /var/www/luboss-vb/ui
npm run build
sudo systemctl restart luboss-frontend

# Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
```

### Issue: Backend 500 Errors

**Check logs:**
```bash
sudo journalctl -u luboss-backend -n 100 --no-pager | grep -i error
```

**Common causes:**
- Missing environment variables → Check `app/.env`
- Database connection issues → Check `DATABASE_URL` in `app/.env`
- Import errors → Check Python dependencies: `pip list`

### Issue: Enum Value Errors

**If you see errors like:**
```
invalid input value for enum penaltyrecordstatus: "PAID"
```

**Solution:**
1. Verify enum values match:
   ```bash
   # On server
   sudo -u postgres psql -d village_bank -c "
   SELECT enumlabel 
   FROM pg_enum 
   WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'penaltyrecordstatus')
   ORDER BY enumsortorder;"
   ```

2. Should show: `pending`, `approved`, `paid` (lowercase)

3. If uppercase values exist, run migration:
   ```bash
   cd /var/www/luboss-vb
   source app/venv/bin/activate
   alembic upgrade head
   ```

### Issue: Services Won't Start

**Check for errors:**
```bash
# Backend
sudo systemctl status luboss-backend
sudo journalctl -u luboss-backend -n 100

# Frontend
sudo systemctl status luboss-frontend
sudo journalctl -u luboss-frontend -n 100
```

**Common fixes:**
- Port conflicts → Check if ports 3000/8002 are in use: `sudo lsof -i:3000 -i:8002`
- Missing dependencies → `cd /var/www/luboss-vb/app && source venv/bin/activate && pip install -r requirements.txt`
- Permission issues → `sudo chown -R teddy:teddy /var/www/luboss-vb`

## Post-Deployment Checklist

- [ ] Backend service is running
- [ ] Frontend service is running
- [ ] API health check returns 200
- [ ] Frontend loads in browser
- [ ] No errors in service logs
- [ ] Database connection works
- [ ] Enum values are correct (if updated)
- [ ] Test login functionality
- [ ] Test a key feature (e.g., view penalties)

## Quick Test Script

Save this as `test_deployment.sh` on the server:

```bash
#!/bin/bash
echo "=== Deployment Verification ==="
echo ""
echo "1. Service Status:"
sudo systemctl is-active luboss-backend && echo "✅ Backend: Running" || echo "❌ Backend: Not Running"
sudo systemctl is-active luboss-frontend && echo "✅ Frontend: Running" || echo "❌ Frontend: Not Running"
echo ""
echo "2. API Health Check:"
curl -s https://luboss95vb.com/test/api/health && echo "" || echo "❌ API not responding"
echo ""
echo "3. Frontend Check:"
curl -s -o /dev/null -w "Status: %{http_code}\n" https://luboss95vb.com/test
echo ""
echo "4. Recent Errors (Backend):"
sudo journalctl -u luboss-backend -n 20 --no-pager | grep -i error | tail -5
echo ""
echo "5. Recent Errors (Frontend):"
sudo journalctl -u luboss-frontend -n 20 --no-pager | grep -i error | tail -5
```

Run with: `chmod +x test_deployment.sh && ./test_deployment.sh`
