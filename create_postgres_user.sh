#!/bin/bash
# Script to create PostgreSQL user for Village Banking

read -p "Enter username for database (default: teddy): " DB_USER
DB_USER=${DB_USER:-teddy}

read -sp "Enter password for $DB_USER: " DB_PASSWORD
echo

read -p "Create user $DB_USER? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "Cancelled."
    exit 0
fi

/opt/homebrew/opt/postgresql@17/bin/psql postgres << SQL
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
ALTER USER $DB_USER CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE village_bank TO $DB_USER;
\q
SQL

echo "User $DB_USER created successfully!"
echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost/village_bank"
