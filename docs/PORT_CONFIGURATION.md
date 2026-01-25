# Port Configuration and Production Integration

## Port Usage Summary

### Production Server (Root `/`)
- **Port 80**: Nginx HTTP (redirects to HTTPS)
- **Port 443**: Nginx HTTPS
- **Port 5000**: Flask/Gunicorn (socket-based, not port-based for external access)
- **Port 5432**: PostgreSQL (localhost only)
- **Port 3306**: MySQL (if used)

### Test Deployment (`/test` subdirectory)
- **Port 8002**: FastAPI backend (NEW - verified available)
- **Port 3000**: Next.js frontend (NEW - verified available)

## Port Conflict Prevention

The deployment script automatically verifies that ports 8002 and 3000 are available before deployment:

```bash
# The script checks:
sudo lsof -i:8002  # Must return nothing
sudo lsof -i:3000  # Must return nothing
```

If either port is in use, the deployment will:
- **In normal mode**: Exit with error and instructions
- **In dry-run mode**: Show warning but continue analysis

## Production Integration

### Nginx Configuration

The production Nginx configuration handles:

1. **Root path (`/`)**:
   - `/api` → Flask/Gunicorn socket (`/var/apps/luboss_api/luboss_api.sock`)
   - `/` → Static React frontend (`/var/www/html/luboss_ui`)

2. **Test path (`/test`)** - Added by deployment:
   - `/test/api` → FastAPI backend (port 8002)
   - `/test` → Next.js frontend (port 3000)

### Integration Steps

1. **Deployment script** copies `deploy/nginx-luboss.conf` to `/etc/nginx/sites-available/luboss-vb`

2. **Manual step required**: Add this line to your existing production server block:
   ```nginx
   # Inside your existing server block at /etc/nginx/sites-available/lubossvb.com
   include /etc/nginx/sites-available/luboss-vb;
   ```

3. **Location**: Add the include **after** your existing `/api` and `/` location blocks to ensure proper precedence.

### Example Production Server Block

```nginx
server {
    listen 443 ssl;
    server_name lubossvb.com www.lubossvb.com;
    
    ssl_certificate /etc/ssl/luboss/certificate.crt;
    ssl_certificate_key /etc/ssl/luboss/private.key;
    
    # Existing production API (socket-based)
    location /api {
        include proxy_params;
        proxy_pass http://unix:/var/apps/luboss_api/luboss_api.sock;
    }
    
    # Existing production frontend (static files)
    location / {
        root /var/www/html/luboss_ui;
        index index.html;
        try_files $uri /index.html;
    }
    
    # Include test deployment configuration
    include /etc/nginx/sites-available/luboss-vb;
}
```

## Service Isolation

The test deployment uses separate systemd services:
- `luboss-backend.service` - FastAPI on port 8002
- `luboss-frontend.service` - Next.js on port 3000

These are completely independent from production:
- Production Flask/Gunicorn runs via socket (no port conflict)
- Test deployment uses ports 8002 and 3000 (verified available)
- Both can run simultaneously without conflicts

## Verification Commands

Before deployment, verify ports:

```bash
# Check if ports are available
sudo lsof -i:8002
sudo lsof -i:3000

# Check all listening ports
sudo lsof -i -P -n | grep LISTEN
```

After deployment, verify services:

```bash
# Check test deployment services
sudo systemctl status luboss-backend
sudo systemctl status luboss-frontend

# Check if ports are listening
sudo lsof -i:8002
sudo lsof -i:3000
```

## Troubleshooting

### Port Already in Use

If you see:
```
Port 8002 is already in use!
```

Options:
1. **Free the port**: Find and stop the process using the port
2. **Change port**: Update `BACKEND_PORT` in `deploy.conf` to an available port
3. **Check conflicts**: Run `sudo lsof -i:8002` to see what's using it

### Nginx Configuration Conflicts

If `/test` paths don't work:
1. Verify the include line is in your production server block
2. Check Nginx config: `sudo nginx -t`
3. Reload Nginx: `sudo systemctl reload nginx`
4. Check Nginx error logs: `sudo tail -f /var/log/nginx/lubossvb.com_error.log`

### Service Conflicts

If services fail to start:
1. Check service logs: `sudo journalctl -u luboss-backend -f`
2. Verify ports are free: `sudo lsof -i:8002`
3. Check service files: `cat /etc/systemd/system/luboss-backend.service`
