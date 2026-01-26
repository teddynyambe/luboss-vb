# How to Check Database Data

## Check User Table

### Basic Query

```bash
# Connect to database and list all users
sudo -u postgres psql -d village_bank -c "SELECT * FROM \"user\";"

# Or with better formatting
sudo -u postgres psql -d village_bank -c "\x" -c "SELECT * FROM \"user\";"
```

### Check Specific Columns

```bash
# Check user emails and names
sudo -u postgres psql -d village_bank -c "SELECT id, email, first_name, last_name, created_at FROM \"user\";"

# Check user with approval status
sudo -u postgres psql -d village_bank -c "
SELECT u.id, u.email, u.first_name, u.last_name, mp.status, mp.approved_at 
FROM \"user\" u 
LEFT JOIN member_profile mp ON u.id = mp.user_id;"
```

### Count Users

```bash
# Count total users
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM \"user\";"

# Count by status
sudo -u postgres psql -d village_bank -c "
SELECT mp.status, COUNT(*) 
FROM member_profile mp 
GROUP BY mp.status;"
```

### Check User Roles

```bash
# Check users and their roles
sudo -u postgres psql -d village_bank -c "
SELECT u.email, r.name as role_name
FROM \"user\" u
JOIN user_role ur ON u.id = ur.user_id
JOIN role r ON ur.role_id = r.id;"
```

## Interactive Database Session

For more complex queries, use an interactive session:

```bash
# Connect to database
sudo -u postgres psql -d village_bank

# Then run SQL commands:
SELECT * FROM "user";
SELECT * FROM member_profile;
SELECT * FROM role;
SELECT * FROM user_role;

# Exit with \q
```

## Check All Tables

```bash
# List all tables
sudo -u postgres psql -d village_bank -c "\dt"

# List all tables with sizes
sudo -u postgres psql -d village_bank -c "\dt+"

# Count rows in each table
sudo -u postgres psql -d village_bank -c "
SELECT 
    schemaname,
    tablename,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = tablename) as column_count
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY tablename;"
```

## Common Queries

### Find User by Email

```bash
sudo -u postgres psql -d village_bank -c "
SELECT * FROM \"user\" WHERE email = 'your-email@example.com';"
```

### Check Recent Registrations

```bash
sudo -u postgres psql -d village_bank -c "
SELECT email, first_name, last_name, created_at 
FROM \"user\" 
ORDER BY created_at DESC 
LIMIT 10;"
```

### Check User with Member Profile

```bash
sudo -u postgres psql -d village_bank -c "
SELECT 
    u.id,
    u.email,
    u.first_name,
    u.last_name,
    mp.status,
    mp.approved,
    mp.approved_at,
    mp.approved_by
FROM \"user\" u
LEFT JOIN member_profile mp ON u.id = mp.user_id;"
```

## Quick Diagnostic Script

```bash
#!/bin/bash
echo "=== User Count ==="
sudo -u postgres psql -d village_bank -t -c "SELECT COUNT(*) FROM \"user\";"

echo -e "\n=== Recent Users ==="
sudo -u postgres psql -d village_bank -c "
SELECT email, first_name, last_name, created_at 
FROM \"user\" 
ORDER BY created_at DESC 
LIMIT 5;"

echo -e "\n=== Users with Member Profiles ==="
sudo -u postgres psql -d village_bank -c "
SELECT u.email, mp.status, mp.approved
FROM \"user\" u
LEFT JOIN member_profile mp ON u.id = mp.user_id
LIMIT 10;"

echo -e "\n=== User Roles ==="
sudo -u postgres psql -d village_bank -c "
SELECT u.email, r.name as role
FROM \"user\" u
JOIN user_role ur ON u.id = ur.user_id
JOIN role r ON ur.role_id = r.id;"
```

Save as `check_db.sh`, make executable, and run:
```bash
chmod +x check_db.sh
./check_db.sh
```
