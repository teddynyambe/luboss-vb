#!/bin/bash
# Manual PostgreSQL user creation script

echo "=== PostgreSQL User Creation ==="
echo ""
echo "Option 1: Use your Mac username (teddy) - No password needed"
echo "  DATABASE_URL=postgresql://teddy@localhost/village_bank"
echo ""
echo "Option 2: Create a new user with password"
echo ""
read -p "Enter new username (or press Enter to skip): " NEW_USER

if [ -z "$NEW_USER" ]; then
    echo "Skipping user creation. Using existing user 'teddy'."
    exit 0
fi

read -sp "Enter password for $NEW_USER: " NEW_PASSWORD
echo ""

/opt/homebrew/opt/postgresql@17/bin/psql postgres << SQL
CREATE USER $NEW_USER WITH PASSWORD '$NEW_PASSWORD';
ALTER USER $NEW_USER CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE village_bank TO $NEW_USER;
\q
SQL

echo ""
echo "✓ User $NEW_USER created!"
echo ""
echo "Update app/.env with:"
echo "DATABASE_URL=postgresql://$NEW_USER:$NEW_PASSWORD@localhost/village_bank"
