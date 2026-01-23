# Mac Setup Guide

## Project Structure

- **Backend**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/app`
- **UI**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/ui`
- **Virtual Environment**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/app/venv`

## Prerequisites

### 1. Install PostgreSQL with pgvector

**Using Homebrew (Recommended)**

```bash
# Install PostgreSQL 17 (pgvector works with 17+)
brew install postgresql@17 pgvector

# Start PostgreSQL service
brew services start postgresql@17

# Add PostgreSQL to PATH (add to ~/.zshrc)
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Create database
createdb village_bank

# Connect to database and enable pgvector
psql village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**Note**: If you have PostgreSQL 15, upgrade to 17+ for pgvector support:
```bash
brew install postgresql@17
brew services stop postgresql@15
brew services start postgresql@17
createdb village_bank
psql village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Set Up Python Virtual Environment

```bash
# Navigate to project root directory
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb

# Create virtual environment in app directory
python3 -m venv app/venv

# Activate virtual environment
source app/venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r app/requirements.txt
```

### 3. Configure Environment Variables

```bash
# From project root, copy example env file
cp .env.example .env

# Edit .env file with your settings
nano .env  # or use your preferred editor
```

Update these values in `.env`:
```env
DATABASE_URL=postgresql://your_username@localhost/village_bank
SECRET_KEY=your-secret-key-here-change-in-production
GROQ_API_KEY=your-groq-api-key
OPENAI_API_KEY=your-openai-api-key
```

**Note**: Your Mac username (from `whoami`) is typically used as the PostgreSQL username. If you need to create a specific user:
```bash
psql postgres -c "CREATE USER your_username WITH PASSWORD 'your_password';"
psql postgres -c "ALTER DATABASE village_bank OWNER TO your_username;"
```

### 4. Run Database Migrations

```bash
# From project root, activate virtual environment
source app/venv/bin/activate

# Create initial migration
alembic revision --autogenerate -m "Initial schema"

# Apply migrations
alembic upgrade head
```

### 5. Seed Initial Data

```bash
# From project root, with venv activated
source app/venv/bin/activate
python scripts/seed_data.py
```

### 6. Run the Application

```bash
# From project root, with venv activated
source app/venv/bin/activate

# Start the FastAPI server
cd app
uvicorn main:app --reload

# Or from project root:
uvicorn app.main:app --reload

# The API will be available at:
# http://localhost:8000
# API docs at: http://localhost:8000/docs
```

## Troubleshooting

### PostgreSQL Connection Issues

If you get connection errors:

1. **Check if PostgreSQL is running**:
   ```bash
   brew services list
   # Should show postgresql@17 as "started"
   ```

2. **Check your username**:
   ```bash
   whoami
   # Use this as the username in DATABASE_URL
   ```

3. **Test connection**:
   ```bash
   psql -d village_bank
   # If this works, your connection is fine
   ```

### pgvector Installation Issues

pgvector is now included with PostgreSQL 17+ via Homebrew. If you're using PostgreSQL 15, upgrade to 17+:
```bash
brew install postgresql@17
brew services stop postgresql@15
brew services start postgresql@17
createdb village_bank
psql village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Python Package Issues

If you encounter import errors:

```bash
# Make sure virtual environment is activated
source app/venv/bin/activate

# Reinstall packages
pip install --upgrade -r app/requirements.txt
```

### Port Already in Use

If port 8000 is already in use:

```bash
# Use a different port
uvicorn app.main:app --reload --port 8001
```

## Quick Start Commands

```bash
# Navigate to project root
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb

# Activate virtual environment
source app/venv/bin/activate

# Start PostgreSQL (if using Homebrew)
brew services start postgresql@17

# Run migrations
alembic upgrade head

# Seed data
python scripts/seed_data.py

# Start server (from project root)
uvicorn app.main:app --reload

# Or from app directory:
cd app
uvicorn main:app --reload
```

## Development Workflow

1. **Navigate to project root**: `cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb`
2. **Activate virtual environment**: `source app/venv/bin/activate`
3. **Make code changes** in `app/` directory
4. **Create migration** (if models changed): `alembic revision --autogenerate -m "Description"`
5. **Apply migration**: `alembic upgrade head`
6. **Restart server**: The `--reload` flag auto-reloads on code changes

## Next Steps

1. Place your `constitution.pdf` in `docs/source/`
2. Place your `collateral_policy.md` in `docs/source/`
3. Test the API at http://localhost:8000/docs
4. Register a test user via `/api/auth/register`
5. Create an admin user and assign roles
