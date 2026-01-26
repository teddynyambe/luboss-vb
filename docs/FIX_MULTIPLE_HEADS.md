# Fix: Multiple Alembic Head Revisions

## Problem

Alembic has multiple head revisions (migration branches) that need to be merged.

## Step 1: Check Current Heads

```bash
# List all head revisions
alembic heads

# Show current revision
alembic current

# Show migration history
alembic history
```

## Step 2: Merge the Heads

You need to create a merge migration that combines all heads:

```bash
# Merge all heads into one
alembic merge heads -m "merge multiple heads"

# This will create a new migration file that merges all heads
```

## Step 3: Upgrade to the New Head

```bash
# After merging, upgrade to head
alembic upgrade head
```

## Alternative: Upgrade to All Heads

If you just want to apply all heads without merging:

```bash
# Upgrade to all heads (applies all branches)
alembic upgrade heads
```

Note: This applies all heads but doesn't merge them. For a clean migration history, merging is better.

## Complete Fix Process

```bash
# 1. Check what heads exist
alembic heads

# 2. Check current state
alembic current

# 3. Merge all heads
alembic merge heads -m "merge multiple heads"

# 4. Upgrade to the merged head
alembic upgrade head

# 5. Verify
alembic current
```

## If Merge Fails

If there are conflicts, you may need to manually resolve them:

1. Check the migration files in `alembic/versions/`
2. Look for the head revisions
3. Manually create a merge migration if needed

## Quick Fix

If you just want to get the database up and running quickly:

```bash
# Apply all heads (doesn't merge, but gets everything applied)
alembic upgrade heads
```

Then later you can clean up the migration history by merging.
