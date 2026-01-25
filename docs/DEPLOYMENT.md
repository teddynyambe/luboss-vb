# Deployment Guide

## Overview

This guide covers deploying Luboss95 Village Banking v2 to a Linux server. The deployment is configured to run at `/test` subdirectory to avoid conflicts with production running on the root path.

## Prerequisites

## Prerequisites

### Server Requirements

- Linux server (Ubuntu 20.04+ recommended)
- Python 3.11+
- Node.js 18+
- PostgreSQL 17+ with pgvector extension
- **Nginx (already installed and running)**
- **SSL certificates (already configured - custom or Let's Encrypt)**
- systemd
- Git
- SSH access to server

### Port Requirements

The deployment uses the following ports (verify they're available):
- **Port 8002**: FastAPI backend (must be free)
- **Port 3000**: Next.js frontend (must be free)

**Production ports already in use** (do not conflict):
- Port 80: Nginx HTTP
- Port 443: Nginx HTTPS
- Port 5000: Production Flask/Gunicorn (socket-based, not port-based)
- Port 5432: PostgreSQL (localhost only)
- Port 3306: MySQL (if used)

**Verification**:
```bash
# Check if ports are available
sudo lsof -i:8002  # Should return nothing
sudo lsof -i:3000  # Should return nothing
```

### Local Machine Requirements

- `bash` (4.0+)
- `git`
- `sshpass` (for password authentication) or SSH keys configured
- `rsync` (optional, for file transfers)

## Initial Server Setup

### 1. Clone Repository on Server

```bash
# SSH into your server
ssh user@your-server.com

# Clone the repository
sudo mkdir -p /var/www
cd /var/www
sudo git clone https://github.com/your-username/luboss-vb.git
sudo chown -R www-data:www-data /var/www/luboss-vb
```

### 2. Run Server Setup Script

```bash
# On the server, run the setup script
cd /var/www/luboss-vb
sudo bash scripts/setup_server.sh
```

This script will:
- Install Python 3.11+ and Node.js 18+
- Check for existing Nginx and SSL certificates
- Create Python virtual environment
- Install systemd service files
- Create environment file templates

**Note**: The script detects existing Nginx and SSL certificates and does not modify them.

### 3. Configure Environment Variables

#### Backend Environment

```bash
# Edit backend environment file
sudo nano /var/www/luboss-vb/app/.env.production
```

Fill in:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT secret key (generate a strong random string)
- `GROQ_API_KEY` - Groq API key for AI chat
- `OPENAI_API_KEY` - OpenAI API key for embeddings
- Other optional settings (SMTP, etc.)

#### Frontend Environment

```bash
# Edit frontend environment file
sudo nano /var/www/luboss-vb/ui/.env.production
```

Set:
- `NEXT_PUBLIC_BASE_PATH=/test`
- `NEXT_PUBLIC_API_URL=https://lubossvb.com/test/api`

### 4. Setup Database

```bash
# Create database (if not exists)
sudo -u postgres createdb village_bank

# Run migrations
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic upgrade head

# Seed initial data (optional)
python scripts/seed_data.py
```

### 5. Configure Nginx

The Nginx configuration is designed to integrate with your existing Nginx setup.

#### Option A: Include in Existing Server Block

Add to your existing server block in `/etc/nginx/sites-available/your-site`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # Your existing SSL configuration
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # Your existing production site configuration for root / remains here
    location / {
        # ... existing production config ...
    }
    
    # Include Luboss configuration for /test
    include /etc/nginx/sites-available/luboss-vb;
}
```

#### Option B: Separate Server Block (Alternative)

If you prefer a separate server block, create `/etc/nginx/sites-available/luboss-vb` with full server block:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # Include location blocks
    include /etc/nginx/sites-available/luboss-vb-locations;
}
```

Then copy the location blocks from `deploy/nginx-luboss.conf` to the locations file.

#### Test and Reload Nginx

```bash
# Test configuration
sudo nginx -t

# If successful, reload
sudo systemctl reload nginx
```

### 6. Install and Start Services

```bash
# Copy systemd service files
sudo cp /var/www/luboss-vb/deploy/luboss-backend.service /etc/systemd/system/
sudo cp /var/www/luboss-vb/deploy/luboss-frontend.service /etc/systemd/system/

# Update service file paths if needed (edit DEPLOY_DIR)
sudo nano /etc/systemd/system/luboss-backend.service
sudo nano /etc/systemd/system/luboss-frontend.service

# Reload systemd
sudo systemctl daemon-reload

# Start services
sudo systemctl start luboss-backend
sudo systemctl start luboss-frontend

# Enable services to start on boot
sudo systemctl enable luboss-backend
sudo systemctl enable luboss-frontend

# Check status
sudo systemctl status luboss-backend
sudo systemctl status luboss-frontend
```

## Local Machine Configuration

### 1. Create Deployment Configuration

```bash
# Copy example configuration
cp deploy.conf.example deploy.conf

# Edit with your server details
nano deploy.conf
```

Fill in:
- `SERVER_HOST` - Your server IP or domain
- `SERVER_USER` - SSH username
- `SSH_PASSWORD` - SSH password (or use SSH keys)
- `DOMAIN` - Your domain name
- `SSL_CERT_PATH` - Path to SSL certificates (e.g., `/etc/letsencrypt/live/your-domain.com`)
- `DEPLOY_PATH` - `/test` (default)
- `DEPLOY_DIR` - `/var/www/luboss-vb` (default)

### 2. Install sshpass (for password authentication)

**macOS**:
```bash
brew install sshpass
```

**Linux**:
```bash
sudo apt-get install sshpass
```

**Alternative**: Use SSH keys (recommended):
```bash
ssh-copy-id user@your-server.com
```

Then remove `SSH_PASSWORD` from `deploy.conf`.

## Deployment Process

### Deploy Changes

```bash
# 1. Make your changes and commit
git add .
git commit -m "Your changes"
git push

# 2. Deploy to server
./deploy.sh
```

The deployment script will:
1. Test SSH connection
2. Pull latest code from git
3. Update Next.js configuration with `basePath: '/test'`
4. Update environment variables
5. Run database migrations
6. Update Python dependencies
7. Build frontend (compiles to optimized JavaScript bundles)
8. Update and reload Nginx configuration
9. Restart backend and frontend services
10. Verify deployment

### What Gets Deployed

**Backend**:
- Python code (FastAPI application)
- Runs as systemd service on port 8002
- Requires Python virtual environment

**Frontend**:
- Next.js compiles to optimized JavaScript bundles
- Static pages: Pre-rendered HTML/CSS/JS
- Dynamic pages: Require Node.js runtime
- Runs as systemd service on port 3000
- Served via Nginx reverse proxy at `/test`

**Database**:
- Migrations run automatically
- No data loss (migrations are additive)

## URL Structure

After deployment, the application will be available at:

- **Frontend**: `https://your-domain.com/test/`
- **Login**: `https://your-domain.com/test/login`
- **Dashboard**: `https://your-domain.com/test/dashboard`
- **API**: `https://your-domain.com/test/api/auth/login`

## Environment Variables

### Build-Time Variables (`NEXT_PUBLIC_*`)

These are embedded into JavaScript bundles during `next build`:
- `NEXT_PUBLIC_API_URL` - API endpoint URL

**Location**: `ui/.env.production` on server
**When set**: Before running `npm run build`
**How**: Deployment script automatically sets this from `deploy.conf`

### Runtime Variables

**Backend**:
- Database connection, JWT secrets, API keys
- **Location**: `app/.env.production` on server
- **When set**: Before starting backend service

**Frontend**:
- Server-side only variables (rarely needed for Next.js)
- **Location**: `ui/.env.production` on server

## Service Management

### Check Service Status

```bash
# Backend
sudo systemctl status luboss-backend

# Frontend
sudo systemctl status luboss-frontend
```

### View Logs

```bash
# Backend logs
sudo journalctl -u luboss-backend -f

# Frontend logs
sudo journalctl -u luboss-frontend -f
```

### Restart Services

```bash
# Restart both
sudo systemctl restart luboss-backend
sudo systemctl restart luboss-frontend

# Or use deployment script (recommended)
./deploy.sh
```

## Troubleshooting

### Deployment Fails

1. **SSH Connection Issues**:
   - Check `SERVER_HOST`, `SERVER_USER`, `SSH_PORT` in `deploy.conf`
   - Test SSH manually: `ssh user@server`
   - Install `sshpass` or configure SSH keys

2. **Git Pull Fails**:
   - Ensure server has access to git repository
   - Check git credentials on server
   - Verify branch name in `deploy.conf`

3. **Database Migration Fails**:
   - Check database connection in `app/.env.production`
   - Verify PostgreSQL is running: `sudo systemctl status postgresql`
   - Check database exists: `psql -l | grep village_bank`

4. **Build Fails**:
   - Check Node.js version: `node -v` (should be 18+)
   - Check npm dependencies: `cd ui && npm install`
   - Check for build errors in deployment output

5. **Service Won't Start**:
   - Check service logs: `sudo journalctl -u luboss-backend -n 50`
   - Verify environment variables are set
   - Check file permissions: `ls -la /var/www/luboss-vb`
   - Verify virtual environment: `source app/venv/bin/activate && which python`

### Nginx Issues

1. **Configuration Test Fails**:
   ```bash
   sudo nginx -t
   ```
   - Fix syntax errors shown
   - Check SSL certificate paths
   - Verify paths in configuration

2. **502 Bad Gateway**:
   - Check if backend is running: `sudo systemctl status luboss-backend`
   - Check backend logs: `sudo journalctl -u luboss-backend -n 50`
   - Verify backend is listening: `curl http://localhost:8002/health`

3. **404 Not Found**:
   - Check if frontend is running: `sudo systemctl status luboss-frontend`
   - Verify Next.js basePath matches Nginx location
   - Check frontend logs: `sudo journalctl -u luboss-frontend -n 50`

### Application Issues

1. **CORS Errors**:
   - Update backend CORS in `app/main.py` to allow your domain
   - Check `NEXT_PUBLIC_API_URL` matches actual API endpoint

2. **Database Connection Errors**:
   - Verify `DATABASE_URL` in `app/.env.production`
   - Check PostgreSQL is running and accessible
   - Verify database user permissions

3. **Authentication Issues**:
   - Check `SECRET_KEY` is set in `app/.env.production`
   - Verify JWT token expiration settings

## Rollback Procedure

If deployment causes issues:

```bash
# SSH into server
ssh user@server

# Rollback git to previous commit
cd /var/www/luboss-vb
git log  # Find previous working commit
git checkout <previous-commit-hash>

# Rebuild frontend
cd ui
npm run build

# Restart services
sudo systemctl restart luboss-backend
sudo systemctl restart luboss-frontend
```

## Security Considerations

1. **SSH Keys**: Use SSH keys instead of passwords when possible
2. **Environment Files**: Never commit `.env` or `.env.production` files
3. **SSL Certificates**: Keep certificates updated (certbot auto-renewal)
4. **Firewall**: Ensure only necessary ports are open (22, 80, 443)
5. **Service User**: Services run as `www-data` user (non-root)
6. **File Permissions**: Ensure proper file ownership and permissions

## Maintenance

### Regular Updates

1. Pull latest code: `git pull`
2. Run migrations: `alembic upgrade head`
3. Update dependencies: `pip install -r app/requirements.txt` and `npm install`
4. Rebuild frontend: `npm run build`
5. Restart services: `systemctl restart luboss-backend luboss-frontend`

### Database Backups

```bash
# Backup database
pg_dump village_bank > backup_$(date +%Y%m%d).sql

# Restore database
psql village_bank < backup_20250123.sql
```

### Log Rotation

Systemd handles log rotation automatically. Logs are stored in journald and can be viewed with `journalctl`.

## Next Steps

After successful deployment:

1. Test the application at `https://your-domain.com/test`
2. Verify API endpoints at `https://your-domain.com/test/api/health`
3. Test login functionality
4. Monitor logs for any errors
5. Set up monitoring and alerts (optional)

## Support

For issues or questions:
- Check logs: `sudo journalctl -u luboss-backend -f`
- Review deployment script output for errors
- Verify all environment variables are set correctly
- Check Nginx error logs: `sudo tail -f /var/log/nginx/error.log`
