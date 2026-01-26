# Fix: Alembic Version String Too Long

## Problem

The revision ID `change_interest_rate_to_effective` (32 characters) is too long for the `alembic_version.version_num` column which is `VARCHAR(32)`.

## Solution

We need to increase the length of the `version_num` column in the `alembic_version` table.

## Fix on Server

Run these commands on your server:

```bash
# Connect to database and increase the column length
sudo -u postgres psql -d village_bank -c "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(50);"

# Verify the change
sudo -u postgres psql -d village_bank -c "\d alembic_version"
```

## Then Run Migrations Again

```bash
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic upgrade head
```

## Alternative: Check Current Column Size

If you want to see what the current size is:

```bash
sudo -u postgres psql -d village_bank -c "SELECT character_maximum_length FROM information_schema.columns WHERE table_name = 'alembic_version' AND column_name = 'version_num';"
```

## Complete Fix

```bash
# 1. Increase column size
sudo -u postgres psql -d village_bank -c "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(50);"

# 2. Run migrations
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic upgrade head

# 3. If successful, restart backend
sudo systemctl restart luboss-backend

# 4. Check backend logs
sudo journalctl -u luboss-backend -n 20 --no-pager
```

The column needs to be at least 32 characters, but 50 is safer for future revision IDs.
