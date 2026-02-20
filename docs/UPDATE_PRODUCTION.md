# Updating Production with Latest Changes from GitHub

This guide explains how to pull the latest code changes from GitHub to your production server, especially when production has been edited directly (e.g., `.env` files, manual configuration changes).

## Quick Update (Recommended)

The easiest way is to use the deployment script, which handles git pulls and service restarts:

```bash
# From your local machine
./deploy.sh
```

The script will:
1. Pull the latest code from GitHub
2. Rebuild the frontend if needed
3. Restart backend and frontend services
4. Handle environment variables safely

## Manual Update on Server

If you prefer to update manually on the server:

### Step 1: SSH to Production Server

```bash
ssh teddy@luboss95vb.com
```

### Step 2: Navigate to Deployment Directory

```bash
cd /var/www/luboss-vb
```

### Step 3: Check for Local Changes

```bash
# Check what files have been modified locally
git status

# See what changes would be overwritten
git diff
```

### Step 4: Stash or Backup Local Changes (if needed)

**Important:** Files that should NOT be overwritten:
- `app/.env` (contains database credentials, secrets)
- `ui/.env.production` (contains frontend environment variables)
- Any manual configuration files

**Option A: Stash local changes temporarily**
```bash
# Stash local changes (saves them temporarily)
git stash

# Pull latest changes
git pull origin main

# Reapply stashed changes (if any)
git stash pop
```

**Option B: Backup important files first**
```bash
# Backup .env files
cp app/.env app/.env.backup
cp ui/.env.production ui/.env.production.backup

# Pull latest changes
git pull origin main

# Restore .env files if they were overwritten
cp app/.env.backup app/.env
cp ui/.env.production.backup ui/.env.production
```

### Step 5: Pull Latest Changes

```bash
# Pull from main branch
git pull origin main

# Or if you're on a different branch
git pull origin <branch-name>
```

### Step 6: Handle Merge Conflicts (if any)

If there are merge conflicts, Git will show you which files have conflicts:

```bash
# Check conflicted files
git status

# For each conflicted file, edit it to resolve conflicts
# Then mark as resolved:
git add <file>
git commit -m "Resolve merge conflicts"
```

**Important:** If `.env` files have conflicts, keep the production version (the one on the server).

### Step 7: Rebuild Frontend (if needed)

```bash
cd ui
npm install  # Only if package.json changed
npm run build
cd ..
```

### Step 8: Restart Services

```bash
# Restart backend
sudo systemctl restart luboss-backend

# Restart frontend
sudo systemctl restart luboss-frontend

# Check status
sudo systemctl status luboss-backend
sudo systemctl status luboss-frontend
```

### Step 9: Verify Deployment

```bash
# Check backend logs
sudo journalctl -u luboss-backend -n 50 --no-pager

# Check frontend logs
sudo journalctl -u luboss-frontend -n 50 --no-pager

# Test API endpoint
curl https://luboss95vb.com/test/api/health
```

## Handling Specific Scenarios

### Scenario 1: Only Code Changes (No .env Changes)

If you only changed code files (Python, TypeScript, etc.):

```bash
cd /var/www/luboss-vb
git pull origin main
sudo systemctl restart luboss-backend luboss-frontend
```

### Scenario 2: .env Files Were Modified Locally

If `.env` files were edited on the server:

```bash
cd /var/www/luboss-vb

# Backup current .env files
cp app/.env app/.env.production
cp ui/.env.production ui/.env.production.backup

# Pull changes
git pull origin main

# Restore production .env files
cp app/.env.production app/.env
cp ui/.env.production.backup ui/.env.production

# Restart services
sudo systemctl restart luboss-backend luboss-frontend
```

### Scenario 3: Database Migrations Included

If the update includes new Alembic migrations:

```bash
cd /var/www/luboss-vb

# Pull changes
git pull origin main

# Activate virtual environment
source app/venv/bin/activate

# Run migrations
alembic upgrade head

# Restart backend
sudo systemctl restart luboss-backend
```

### Scenario 4: Frontend Dependencies Changed

If `package.json` or `package-lock.json` changed:

```bash
cd /var/www/luboss-vb/ui

# Pull changes (if not done already)
git pull origin main

# Install new dependencies
npm install

# Rebuild
npm run build

# Restart frontend
sudo systemctl restart luboss-frontend
```

## Preventing .env File Conflicts

To prevent `.env` files from being overwritten, you can:

### Option 1: Add to .gitignore (Recommended)

Ensure `.env` files are in `.gitignore`:

```bash
# Check if they're ignored
git check-ignore app/.env ui/.env.production

# If not, add them (from your local machine)
echo "app/.env" >> .gitignore
echo "ui/.env.production" >> .gitignore
git add .gitignore
git commit -m "Add .env files to gitignore"
git push
```

### Option 2: Use Git Update Strategy

Configure git to not overwrite local changes:

```bash
# On server, configure git to keep local changes
cd /var/www/luboss-vb
git config pull.rebase false
git config merge.ours.driver true

# Create a merge driver that keeps local .env files
cat > .git/info/attributes << 'EOF'
app/.env merge=ours
ui/.env.production merge=ours
EOF
```

## Troubleshooting

### Error: "Your local changes would be overwritten"

**Solution:** Stash or commit your changes first:

```bash
# Stash changes
git stash

# Pull
git pull origin main

# Reapply (if needed)
git stash pop
```

### Error: "Merge conflict in .env"

**Solution:** Keep the production version:

```bash
# Use production version
git checkout --ours app/.env
git checkout --ours ui/.env.production

# Mark as resolved
git add app/.env ui/.env.production
git commit -m "Keep production .env files"
```

### Services Won't Start After Update

**Check logs:**
```bash
sudo journalctl -u luboss-backend -n 100 --no-pager
sudo journalctl -u luboss-frontend -n 100 --no-pager
```

**Common issues:**
- Missing environment variables → Check `.env` files
- Database connection errors → Verify `DATABASE_URL` in `app/.env`
- Port conflicts → Check if ports 3000 and 8002 are available

### Frontend Shows Old Version

**Clear browser cache or do a hard refresh:**
- Chrome/Firefox: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
- Or clear browser cache

**Verify frontend was rebuilt:**
```bash
# Check build timestamp
ls -lh /var/www/luboss-vb/ui/.next

# Rebuild if needed
cd /var/www/luboss-vb/ui
npm run build
sudo systemctl restart luboss-frontend
```

## Quick Reference

```bash
# Full update sequence
cd /var/www/luboss-vb
git pull origin main
cd ui && npm install && npm run build && cd ..
sudo systemctl restart luboss-backend luboss-frontend

# Check status
sudo systemctl status luboss-backend luboss-frontend

# View logs
sudo journalctl -u luboss-backend -f
sudo journalctl -u luboss-frontend -f
```

## Best Practices

1. **Always backup .env files** before pulling changes
2. **Test in staging first** if possible
3. **Check git status** before pulling to see what will change
4. **Review changes** with `git log` or `git diff` before pulling
5. **Monitor logs** after restarting services
6. **Keep .env files out of git** to avoid conflicts

---

## Recent Production Updates

### 2026-02-20 — Forgot Password + Cycle Ranges Sort

This release added a self-service password reset flow and fixed cycle interest rate range ordering.

**Steps required after pulling this release:**

```bash
cd /var/www/luboss-vb

# 1. Activate venv and run the new migration
source app/venv/bin/activate
alembic upgrade head
# Adds: password_reset_token, password_reset_expires columns to `user` table

# 2. Add new settings to app/.env (if not already present)
#    FRONTEND_URL=https://luboss95vb.com
#    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / FROM_EMAIL

# 3. Restart backend to load new /forgot-password and /reset-password routes
sudo systemctl restart luboss-backend

# 4. Rebuild and restart frontend (new pages: /forgot-password, /reset-password)
cd ui && npm run build && cd ..
sudo systemctl restart luboss-frontend
```

**Verify:**
```bash
# Check migration applied
mysql -u root luboss -e "DESCRIBE user;" | grep password_reset

# Test the new endpoint
curl -X POST https://luboss95vb.com/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
# Expected: {"message":"If that email is registered, a reset link has been sent."}
```
