# Restart Servers After Changes

After making changes to the backend code, you need to restart the servers:

## Backend Server

```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
source app/venv/bin/activate
uvicorn app.main:app --reload --port 8002
```

Or if already running, stop it (Ctrl+C) and restart.

## Frontend Server

The frontend should auto-reload, but if needed:

```bash
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb/ui
npm run dev
```

## Recent Changes Made

1. **Fixed password hashing** - Changed from passlib to direct bcrypt
2. **Fixed UUID conversion** - Updated `get_current_user` to properly convert string UUID to UUID object
3. **Fixed CORS** - Updated to allow specific frontend origins
4. **Improved error handling** - Better error messages in API client

## Testing Login

After restarting, test the login:
- Email: `admin@villagebank.com`
- Password: `admin123`

The login should now work and redirect to the dashboard.
