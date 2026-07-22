# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

LUBOSS 95 Village Banking v2 — a full-stack microfinance management system for village banking operations with double-entry accounting, role-based access (Admin, Chairman, Vice-Chairman, Treasurer, Compliance, Member), and RAG-based AI chat.

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI 0.128 / SQLAlchemy 2.0 / Pydantic v2 / Alembic
- **Frontend**: Next.js 16 / React 19 / TypeScript 5 / Tailwind CSS 4
- **Database**: **MySQL** (`mysql+pymysql://...`) — this is the production database. Despite `psycopg2-binary` being in `requirements.txt` and the README mentioning PostgreSQL, the deployed system runs on MySQL. UUIDs are stored as `CHAR(32)` (no dashes) via SQLAlchemy `Uuid(as_uuid=True)`, while `JournalEntry.source_ref` is `String(100)` populated with `str(uuid)` so it carries the hyphenated form — keep this in mind when writing raw SQL that joins the two.
- **AI**: Groq (Llama 3.3-70b) for chat, OpenAI (text-embedding-3-small) for embeddings
- **Background tasks**: APScheduler (runs every 5 minutes)

## Development Commands

### Backend
```bash
source app/venv/bin/activate
uvicorn app.main:app --reload --port 8002
```

### Frontend
```bash
cd ui
npm run dev          # Dev server on port 3000
npm run build        # Production build
npm run lint         # ESLint
```

### Database Migrations
```bash
# Create migration
alembic revision --autogenerate -m "description"
# Apply migrations
alembic upgrade head
```

### Seeding
```bash
python scripts/seed_data.py
python scripts/setup_ledger_accounts.py
```

## Architecture

### Backend (`app/`)

The backend follows a layered architecture: **routers → services → models/schemas → database**.

- `api/` — FastAPI routers, one per role (admin, chairman, treasurer, compliance, member, auth, ai). These are large files containing all endpoints for that role.
- `services/` — Business logic layer. Key services:
  - `accounting.py` — Double-entry ledger operations (journal entries with debit/credit lines)
  - `transaction.py` — Declaration, deposit, loan, and repayment workflows
  - `cycle.py` — Financial cycle and phase management
  - `rbac.py` — Role-based access control
  - `scheduler.py` — Background tasks (auto-close loans, transfer excess contributions)
- `models/` — SQLAlchemy ORM models. Core: user, member, ledger, cycle, transaction, policy
- `schemas/` — Pydantic v2 request/response schemas
- `core/` — Config (Pydantic Settings from .env), security (JWT/bcrypt), dependency injection
- `ai/` — RAG pipeline: document ingestion → embeddings → vector retrieval → Groq LLM with tool calling
- `db/base.py` — SQLAlchemy engine, SessionLocal, Base declarative class

### Frontend (`ui/`)

Next.js App Router with file-based routing.

- `app/dashboard/{role}/` — Role-specific dashboard pages
- `components/` — Shared components (FloatingAIChat, modals, UserMenu)
- `contexts/AuthContext.tsx` — JWT auth state management (tokens in localStorage)
- `lib/api.ts` — Centralized API client with JWT header injection
- `lib/memberApi.ts` — Member-specific API helpers

### Key Business Logic

- **Accounting**: Double-entry bookkeeping with chart of accounts (Bank Cash, Loans Receivable, Member Savings, etc.)
- **Declaration workflow**: Member declares monthly contributions → uploads deposit proof → Treasurer approves → posted to ledger
- **Loan workflow**: Member checks eligibility (savings × credit rating multiplier) → applies → Treasurer approves → disbursed → repayments tracked → auto-closed when paid
- **Cycles & Phases**: Financial cycles define time-bounded phases that control when actions are allowed
- **Credit Ratings**: Tiered system (e.g., Low Risk A+) determines borrowing limits per cycle

### Environment Variables

Configuration lives in `app/.env` (see `app/.env.example`). Key vars: `DATABASE_URL`, `SECRET_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `SMTP_*`, `FRONTEND_URL`.

## Deployment

Production deployment uses `deploy.sh` / `deploy.conf` targeting Ubuntu servers with systemd services and Nginx reverse proxy. See `docs/DEPLOYMENT.md`.
