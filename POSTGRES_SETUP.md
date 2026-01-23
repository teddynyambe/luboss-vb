# PostgreSQL User Setup Guide

## Option 1: Use Your Mac Username (Simplest - No Password)

If you want to use your Mac username without a password (trust authentication):

```bash
# Your username is: teddy
# DATABASE_URL would be: postgresql://teddy@localhost/village_bank
```

This works if PostgreSQL is configured for trust authentication for local connections (default on macOS with Homebrew).

## Option 2: Create a New PostgreSQL User with Password

### Method A: Using the Script

```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
./create_postgres_user.sh
```

Follow the prompts to create a user.

### Method B: Manual Creation

```bash
# Connect to PostgreSQL
/opt/homebrew/opt/postgresql@17/bin/psql postgres

# In psql, run:
CREATE USER village_bank_user WITH PASSWORD 'your_secure_password';
ALTER USER village_bank_user CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE village_bank TO village_bank_user;
\q
```

### Method C: Using psql Command Line

```bash
# Create user with password
/opt/homebrew/opt/postgresql@17/bin/psql postgres -c "CREATE USER village_bank_user WITH PASSWORD 'your_secure_password';"

# Grant privileges
/opt/homebrew/opt/postgresql@17/bin/psql postgres -c "ALTER USER village_bank_user CREATEDB;"
/opt/homebrew/opt/postgresql@17/bin/psql village_bank -c "GRANT ALL PRIVILEGES ON DATABASE village_bank TO village_bank_user;"
```

## Update .env File

After creating the user, update `app/.env`:

```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb/app
nano .env  # or use your preferred editor
```

Set the DATABASE_URL:
```env
# For user with password:
DATABASE_URL=postgresql://village_bank_user:your_secure_password@localhost/village_bank

# For Mac username (no password):
DATABASE_URL=postgresql://teddy@localhost/village_bank
```

## Test Connection

```bash
# Test connection with your user
/opt/homebrew/opt/postgresql@17/bin/psql -U village_bank_user -d village_bank

# Or with Mac username:
/opt/homebrew/opt/postgresql@17/bin/psql -U teddy -d village_bank
```

## Troubleshooting

### Authentication Failed

If you get authentication errors, check PostgreSQL's `pg_hba.conf`:

```bash
# Find the config file
/opt/homebrew/opt/postgresql@17/bin/pg_config --sysconfdir

# Edit pg_hba.conf to allow local connections
# Look for lines like:
# local   all   all   trust
# host    all   all   127.0.0.1/32   trust
```

### Permission Denied

If you get permission errors:

```bash
# Grant ownership of database
/opt/homebrew/opt/postgresql@17/bin/psql postgres -c "ALTER DATABASE village_bank OWNER TO your_username;"
```
