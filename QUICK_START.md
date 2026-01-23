# Quick Start Guide

## Server is Running! 🎉

Your Village Banking v2 API is now running at:
- **API**: http://localhost:8002
- **Interactive Docs**: http://localhost:8002/docs
- **Health Check**: http://localhost:8002/health

## Project Structure

- **Backend**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/app`
- **UI**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/ui`
- **Virtual Environment**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/app/venv`
- **Environment File**: `/Users/teddy/vm_shared/teddy/Projects/luboss-vb/app/.env`

## Database

- **PostgreSQL 17** running with pgvector extension
- **Database**: `village_bank`
- **Connection**: `postgresql://teddy@localhost/village_bank`

## Seed Data Loaded

- ✅ 6 Roles (Admin, Chairman, Vice-Chairman, Treasurer, Compliance, Member)
- ✅ 8 Ledger Accounts (Bank Cash, Loans Receivable, Member Savings, Social Fund, Admin Fund, Interest Income, Penalty Income, Carry-Forward)
- ✅ 4 Interest Policies (1mo→10%, 2mo→15%, 3mo→20%, 4mo→25%)
- ✅ Interest Threshold Policies (K25,000 and K50,000 reductions)
- ✅ Credit Rating Scheme with 3 tiers

## Common Commands

### Start Server
```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
source app/venv/bin/activate
uvicorn app.main:app --reload --port 8002
```

### Run Migrations
```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
source app/venv/bin/activate
alembic upgrade head
```

### Create New Migration
```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
source app/venv/bin/activate
alembic revision --autogenerate -m "Description"
```

### Access Database
```bash
psql village_bank
```

## Next Steps

1. **Test the API**: Visit http://localhost:8002/docs to see interactive API documentation
2. **Register a user**: POST to `/api/auth/register`
3. **Login**: POST to `/api/auth/login` to get JWT token
4. **Create admin user**: Manually create an admin user in the database and assign Admin role
5. **Upload constitution**: Place `constitution.pdf` in `docs/source/` and use `/api/chairman/constitution/upload`
6. **Upload collateral policy**: Place `collateral_policy.md` in `docs/source/`

## API Endpoints Summary

- **Auth**: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`
- **Admin**: `/api/admin/settings`, `/api/admin/users`
- **Chairman**: `/api/chairman/pending-members`, `/api/chairman/members/{id}/approve`
- **Treasurer**: `/api/treasurer/deposits/pending`, `/api/treasurer/deposits/{id}/approve`
- **Compliance**: `/api/compliance/penalties`
- **Member**: `/api/member/status`, `/api/member/declarations`, `/api/member/loans/apply`
- **AI Chat**: `/api/ai/chat`

## Troubleshooting

If the server stops, restart it:
```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
source app/venv/bin/activate
uvicorn app.main:app --reload --port 8002
```

If you get import errors, make sure you're running from the project root and the virtual environment is activated.
