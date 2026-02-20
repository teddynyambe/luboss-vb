# Changelog

All notable changes to Luboss95 Village Banking v2 are documented here.

---

## [Unreleased]

---

## [2026-02-20] — Login UI, Forgot Password, Cycle Ranges Sort

### Added
- **Login page card** — login form now renders inside a white rounded card with a blue border, making it visually distinct from the gradient background.
- **Forgot Password flow** — full self-service password reset via email:
  - "Forgot password?" link on login page (`/login`) links to `/forgot-password`.
  - `/forgot-password` — enter email; always shows a generic success message to prevent email enumeration.
  - `/reset-password?token=<token>` — enter and confirm new password using the token from the email link.
  - Token is a `secrets.token_urlsafe(32)` value; stored as SHA-256 hash in the database; expires after **1 hour**.
  - Password reset email sent via SMTP using `app/core/email.py` (plain text + HTML).
- **New API endpoints** (no authentication required):
  - `POST /api/auth/forgot-password` — initiates reset; body: `{ "email": "..." }`.
  - `POST /api/auth/reset-password` — completes reset; body: `{ "token": "...", "new_password": "..." }`.
- **New DB columns** on `user` table:
  - `password_reset_token VARCHAR(255) NULL`
  - `password_reset_expires DATETIME NULL`
- **New Alembic migration**: `e3f4a5b6c7d8_add_password_reset_to_user.py`
- **New config setting**: `FRONTEND_URL` (default `https://luboss95vb.com`) — used to build the reset link in the email.
- **Email utility**: `app/core/email.py` — SMTP with STARTTLS; reads `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `FROM_EMAIL` from `app/.env`.

### Fixed
- **Cycle interest rate ranges sort order** — ranges under each credit rating tier now always display in ascending `term_months` order (NULL catch-all first, then 1 → 2 → 3 → 4). Fixed in both the backend query (`.order_by(term_months.nullsfirst())`) and the frontend mapping (`.sort()` by numeric term_months).

### Files Changed
| File | Change |
|------|--------|
| `ui/app/login/page.tsx` | Card wrapper on form + "Forgot password?" link |
| `ui/app/forgot-password/page.tsx` | **New** — email request page |
| `ui/app/reset-password/page.tsx` | **New** — token + new password page |
| `app/core/email.py` | **New** — SMTP send utility |
| `app/core/config.py` | Added `FRONTEND_URL` setting |
| `app/schemas/auth.py` | Added `PasswordResetRequest`, `PasswordReset` schemas |
| `app/api/auth.py` | Added `forgot-password` and `reset-password` endpoints |
| `app/models/user.py` | Added `password_reset_token`, `password_reset_expires` columns |
| `alembic/versions/e3f4a5b6c7d8_add_password_reset_to_user.py` | **New** — DB migration |
| `app/api/chairman.py` | Added `.order_by(term_months.nullsfirst())` to interest ranges query |
| `ui/app/dashboard/chairman/cycles/page.tsx` | Sort interest_ranges after mapping in `loadCycleForEdit` |

### Production Steps (run once after deploy)
```bash
# SSH into server
ssh teddy@luboss95vb.com
cd /var/www/luboss-vb

# Run DB migration (from project root, venv active)
source app/venv/bin/activate
alembic upgrade head

# Restart backend to pick up new routes
sudo systemctl restart luboss-backend
```

---

## [2026-02-17] — Bank Statement Support

### Added
- Bank statement upload and management for compliance.
- Alembic migration `d1a2b3c4e5f6` adding bank statement table.

---

## [Earlier] — Initial Production Release

- Full cycle management (chairman).
- Loan origination, repayment, penalty tracking.
- Member savings and declarations.
- RBAC with roles: Chairman, Treasurer, Compliance, Admin, Member.
- AI chat with RAG over constitution documents.
- Audit logging.
