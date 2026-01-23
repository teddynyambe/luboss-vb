#!/bin/bash
# Script to run the migration to add CHAIRMAN role to the database enum

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "app/venv" ]; then
    source app/venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the migration
echo "Running migration to add CHAIRMAN role..."
alembic upgrade head

echo "Migration complete!"
