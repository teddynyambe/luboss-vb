# Fix: Missing credit_rating_interest_range Table

## Problem

The `credit_rating_interest_range` table doesn't exist, causing errors when the application tries to query it.

## Solution: Create the Missing Table

The table should be created by migrations, but if it's missing, create it manually:

**On production server:**

```bash
# Create the missing table
sudo -u postgres psql -d village_bank -c "
CREATE TABLE IF NOT EXISTS credit_rating_interest_range (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier_id UUID NOT NULL REFERENCES credit_rating_tier(id),
    cycle_id UUID NOT NULL REFERENCES cycle(id),
    term_months VARCHAR(10),
    effective_rate_percent NUMERIC(5, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_credit_rating_interest_range_tier_id ON credit_rating_interest_range(tier_id);
CREATE INDEX IF NOT EXISTS ix_credit_rating_interest_range_cycle_id ON credit_rating_interest_range(cycle_id);

GRANT ALL PRIVILEGES ON TABLE credit_rating_interest_range TO luboss;
ALTER TABLE credit_rating_interest_range OWNER TO luboss;
"
```

## Verify Table Exists

```bash
# Check table was created
sudo -u postgres psql -d village_bank -c "\d credit_rating_interest_range"

# Check if it has data
sudo -u postgres psql -d village_bank -c "SELECT COUNT(*) FROM credit_rating_interest_range;"
```

## Alternative: Check Migration Status

If the table should be created by a migration, check:

```bash
# Check current migration version
cd /var/www/luboss-vb
source app/venv/bin/activate
alembic current

# Check migration history
alembic history | grep -i "credit_rating_interest"

# If migrations didn't complete, run them again
alembic upgrade head
```

## After Creating Table

Restart the backend:

```bash
sudo systemctl restart luboss-backend
sudo systemctl status luboss-backend --no-pager -l | head -15
```
