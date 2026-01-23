# Luboss95 Village Banking v2 (LUBOSS 95)

A comprehensive FastAPI-based Village Banking system with PostgreSQL, double-entry accounting, RBAC, and AI-powered chat assistance.

## Overview

LUBOSS 95 is a modern microfinance management system designed for village banking operations. It features double-entry accounting, role-based access control, loan management, member declarations, deposit tracking, and an AI assistant constrained to constitution/policies and member account information.

## Features

### Core Functionality
- **Double-entry accounting ledger** for financial accuracy and audit trails
- **Role-Based Access Control (RBAC)** with 6 roles: Admin, Chairman, Vice-Chairman, Treasurer, Compliance, Member
- **RAG-based AI chat** constrained to constitution/rules/policies and member's own account status
- **Loan Management** - Application, approval, disbursement, repayment tracking, and history
- **Member Declarations** - Monthly declarations with deposit proof uploads
- **Cycle Management** - Annual financial cycles with configurable phases
- **Credit Rating System** - Tiered credit ratings with borrowing limits and interest rates
- **Deposit Proof Workflow** - Upload, review, approve/reject with comments
- **Penalty Management** - Compliance tracking and treasurer approval
- **Seamless Migration** - Tools to migrate from legacy MySQL system

### User Interfaces
- **Next.js Frontend** - Modern, mobile-first UI with light blue theme
- **Member Dashboard** - Account status, declarations, loans, deposits
- **Treasurer Dashboard** - Deposit approvals, loan management, active loan monitoring
- **Chairman Dashboard** - Member management, cycle management, user roles
- **Admin Dashboard** - System settings and configuration

## Tech Stack

### Backend
- **Python 3.11+** with FastAPI
- **PostgreSQL 17** with pgvector extension for vector search
- **SQLAlchemy 2.0** (ORM)
- **Alembic** (Database migrations)
- **Pydantic v2** (Data validation)
- **Uvicorn** (ASGI server)

### Frontend
- **Next.js** (React framework)
- **TypeScript**
- **Tailwind CSS** (Styling)
- **React Context API** (State management)

### AI & Search
- **Groq API** with Llama 3.1 70B (LLM)
- **OpenAI** text-embedding-3-small (Embeddings)
- **pgvector** (Vector similarity search)
- **RAG Architecture** (Retrieval Augmented Generation)

## Project Structure

```
luboss-vb/
├── app/                    # Backend application
│   ├── api/                # FastAPI routers
│   │   ├── admin.py        # Admin endpoints
│   │   ├── auth.py         # Authentication
│   │   ├── chairman.py     # Chairman endpoints
│   │   ├── compliance.py   # Compliance endpoints
│   │   ├── member.py       # Member endpoints
│   │   ├── treasurer.py    # Treasurer endpoints
│   │   └── ai.py           # AI chat endpoints
│   ├── core/               # Core configuration
│   │   ├── config.py       # Environment config
│   │   ├── dependencies.py # FastAPI dependencies
│   │   └── security.py     # JWT & password hashing
│   ├── db/                 # Database connection
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business logic
│   │   ├── accounting.py   # Ledger operations
│   │   ├── auth.py         # Authentication logic
│   │   ├── cycle.py        # Cycle management
│   │   ├── member.py       # Member operations
│   │   ├── policy.py       # Policy calculations
│   │   ├── rbac.py         # Role-based access
│   │   └── transaction.py  # Transaction processing
│   ├── ai/                 # AI/RAG functionality
│   │   ├── chat.py         # Chat endpoint
│   │   ├── ingestion.py    # Document ingestion
│   │   ├── retrieval.py   # Vector search
│   │   └── tools.py        # AI tool contracts
│   ├── main.py             # FastAPI app entry point
│   └── requirements.txt    # Python dependencies
│
├── ui/                     # Frontend application
│   ├── app/                # Next.js app directory
│   │   ├── dashboard/      # Dashboard pages
│   │   │   ├── admin/      # Admin dashboard
│   │   │   ├── chairman/   # Chairman dashboard
│   │   │   ├── member/     # Member dashboard
│   │   │   └── treasurer/  # Treasurer dashboard
│   │   ├── login/          # Login page
│   │   ├── register/       # Registration page
│   │   └── pending/        # Pending approval page
│   ├── contexts/           # React contexts
│   ├── lib/                 # Utilities
│   └── package.json        # Node dependencies
│
├── alembic/                # Database migrations
│   └── versions/           # Migration scripts
│
├── docs/                   # Documentation
│   ├── ai/                 # AI/RAG documentation
│   ├── migration/          # Migration guides
│   └── source/             # Source documents (constitution, policies)
│
├── scripts/                # Utility scripts
│   ├── create_admin.py     # Create admin user
│   ├── seed_data.py        # Seed initial data
│   └── setup_ledger_accounts.py  # Setup ledger accounts
│
└── uploads/                # Uploaded files
    ├── constitution/       # Constitution PDFs
    └── deposit_proofs/     # Deposit proof documents
```

## Setup Instructions

### Prerequisites
- Python 3.11 or higher
- PostgreSQL 17 or higher
- Node.js 18+ and npm
- Git

### Backend Setup

1. **Clone the repository**:
```bash
git clone <repository-url>
cd luboss-vb
```

2. **Create and activate virtual environment**:
```bash
cd app
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

4. **Set up PostgreSQL**:
```bash
# Install PostgreSQL and pgvector extension
# See POSTGRES_SETUP.md for detailed instructions

# Create database
createdb village_bank

# Enable pgvector extension
psql village_bank -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

5. **Configure environment**:
```bash
# Copy example env file (if exists) or create .env in app/ directory
cd app
# Edit .env with your settings:
# - DATABASE_URL
# - JWT_SECRET_KEY
# - GROQ_API_KEY
# - OPENAI_API_KEY
# - SMTP settings (if using email)
```

6. **Run database migrations**:
```bash
cd ..
alembic upgrade head
```

7. **Seed initial data**:
```bash
python scripts/seed_data.py
python scripts/setup_ledger_accounts.py
```

8. **Start the backend server**:
```bash
cd app
source venv/bin/activate
uvicorn main:app --reload --port 8002
```

The API will be available at `http://localhost:8002`
API documentation at `http://localhost:8002/docs`

### Frontend Setup

1. **Navigate to UI directory**:
```bash
cd ui
```

2. **Install dependencies**:
```bash
npm install
```

3. **Configure API endpoint** (if needed):
Edit `ui/lib/api.ts` to set the correct backend URL (default: `http://localhost:8002`)

4. **Start the development server**:
```bash
npm run dev
```

The UI will be available at `http://localhost:3000`

## Key Features Documentation

### Loan Management
- Members can apply for loans with notes
- Loan eligibility calculated based on savings and credit rating
- Treasurer approves and disburses loans in one step
- Loan status tracking: Pending → Active → Paid Off
- Full repayment history with principal/interest breakdown
- Loan balance calculation from actual loan records

### Member Declarations
- Monthly declarations (15th-20th of month)
- Declarations can be edited before 20th of month
- Deposit proof upload required
- Treasurer approval workflow with comments
- Automatic ledger posting upon approval

### Cycle Management
- Annual financial cycles
- Configurable phases (deposits, payout, shareout)
- Social Fund and Admin Fund requirements per cycle
- Credit rating schemes per cycle
- Cycle activation/deactivation by Chairman

### Credit Rating System
- Tiered credit ratings (A, B, C, etc.)
- Borrowing multipliers per tier
- Interest rate ranges per tier and loan term
- Assignment to members per cycle

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user (requires admin approval)
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user info

### Member
- `GET /api/member/status` - Get account status (savings, loans, funds, penalties)
- `GET /api/member/cycles` - Get active cycles
- `POST /api/member/declarations` - Create monthly declaration
- `GET /api/member/declarations` - List all declarations
- `GET /api/member/declarations/current-month` - Get current month declaration
- `PUT /api/member/declarations/{id}` - Update declaration
- `POST /api/member/deposits/proof` - Upload deposit proof
- `GET /api/member/deposits` - List deposit proofs
- `POST /api/member/deposits/{id}/respond` - Respond to treasurer comment
- `GET /api/member/loans/eligibility/{cycle_id}` - Get loan eligibility
- `POST /api/member/loans/apply` - Apply for loan
- `GET /api/member/loans` - Get all loans (history)
- `GET /api/member/loans/current` - Get current active loan
- `PUT /api/member/loans/{id}` - Edit pending loan application
- `POST /api/member/loans/{id}/withdraw` - Withdraw loan application

### Treasurer
- `GET /api/treasurer/deposits/pending` - List pending deposit proofs
- `POST /api/treasurer/deposits/{id}/approve` - Approve deposit and post to ledger
- `POST /api/treasurer/deposits/{id}/reject` - Reject deposit with comment
- `GET /api/treasurer/deposits/proof/{filename}` - View deposit proof file
- `GET /api/treasurer/penalties/pending` - List pending penalties
- `POST /api/treasurer/penalties/{id}/approve` - Approve penalty
- `GET /api/treasurer/loans/pending` - List pending loan applications
- `POST /api/treasurer/loans/{id}/approve` - Approve and disburse loan
- `GET /api/treasurer/loans/active` - List active loans
- `GET /api/treasurer/loans/{id}/details` - Get loan performance details

### Chairman
- `GET /api/chairman/pending-members` - List pending members
- `GET /api/chairman/members` - List all members (with filters)
- `POST /api/chairman/members/{id}/approve` - Approve member
- `POST /api/chairman/members/{id}/suspend` - Suspend member
- `POST /api/chairman/members/{id}/activate` - Activate member
- `GET /api/chairman/cycles` - List all cycles
- `POST /api/chairman/cycles` - Create new cycle
- `GET /api/chairman/cycles/{id}` - Get cycle details
- `PUT /api/chairman/cycles/{id}` - Update cycle
- `POST /api/chairman/cycles/{id}/activate` - Activate cycle
- `POST /api/chairman/cycles/{id}/close` - Close cycle
- `POST /api/chairman/cycles/{id}/reopen` - Reopen closed cycle
- `GET /api/chairman/users` - List all users
- `POST /api/chairman/members/{id}/credit-rating` - Assign credit rating
- `GET /api/chairman/credit-rating-tiers/{cycle_id}` - Get credit rating tiers

### Admin
- `GET /api/admin/settings` - Get system settings
- `PUT /api/admin/settings` - Update system settings

### AI Chat
- `POST /api/ai/chat` - AI chat endpoint (RAG with constitution/policies)

## Database Schema

### Core Tables
- `user` - User accounts (preserved from legacy system)
- `member_profile` - Member profiles linked to users
- `user_role` - Role assignments
- `cycle` - Financial cycles
- `cycle_phase` - Cycle phases

### Accounting Tables
- `ledger_account` - Chart of accounts
- `journal_entry` - Journal entry headers
- `journal_line` - Journal entry lines (double-entry)

### Transaction Tables
- `declaration` - Member monthly declarations
- `deposit_proof` - Deposit proof documents
- `deposit_approval` - Treasurer approvals
- `loan_application` - Loan applications
- `loan` - Approved loans
- `repayment` - Loan repayments
- `penalty_record` - Penalty records

### Policy Tables
- `credit_rating_scheme` - Credit rating schemes
- `credit_rating_tier` - Rating tiers
- `member_credit_rating` - Member ratings per cycle
- `credit_rating_interest_range` - Interest rates per tier
- `borrowing_limit_policy` - Borrowing limits

## Migration from Legacy System

See `docs/migration/` for detailed migration guides:
- `mapping.md` - Field mappings
- `rules.md` - Business rules
- `validation_checklist.md` - Validation steps

Migration scripts:
- `scripts/export_old_schema.sh` - Export old schema
- `scripts/migrate_load.py` - Load staging data
- `scripts/migrate_transform.py` - Transform to journals
- `scripts/migrate_validate.py` - Validate migration

## Development

### Running Tests
```bash
# Backend tests (when implemented)
pytest

# Frontend tests (when implemented)
cd ui
npm test
```

### Creating Migrations
```bash
alembic revision --autogenerate -m "Description of changes"
alembic upgrade head
```

### Code Style
- Backend: Follow PEP 8, use type hints
- Frontend: ESLint configuration included

## Deployment

### Production Considerations
- Set `ENVIRONMENT=production` in `.env`
- Use strong `JWT_SECRET_KEY`
- Configure proper CORS origins
- Set up SSL/TLS
- Use production database with backups
- Configure proper file storage for uploads
- Set up monitoring and logging

## License

Proprietary - LUBOSS 95

## Support

For issues and questions, refer to:
- `TROUBLESHOOTING.md` - Common issues and solutions
- `QUICK_START.md` - Quick setup guide
- `SETUP_MAC.md` - Mac-specific setup
- `POSTGRES_SETUP.md` - PostgreSQL setup guide

## Version History

### v1.0.0 (Stable Release)
- Complete loan management system
- Member declarations with deposit proof workflow
- Treasurer dashboard with loan approval and monitoring
- Chairman dashboard with cycle and user management
- Credit rating system with borrowing limits
- Full accounting ledger integration
- AI chat with RAG (constitution/policies)
- Mobile-first responsive UI
