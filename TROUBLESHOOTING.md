# Troubleshooting Login Issues

## Current Issue: CORS and 500 Error

If you're seeing CORS errors and 500 Internal Server Error, follow these steps:

### 1. Restart Backend Server

**IMPORTANT**: The backend server MUST be restarted after code changes:

```bash
# Stop the server (Ctrl+C)
cd /Users/teddy/vm_shared/teddy/Projects/luboss-vb
source app/venv/bin/activate
uvicorn app.main:app --reload --port 8002
```

### 2. Verify Server is Running

```bash
curl http://localhost:8002/health
# Should return: {"status":"healthy"}
```

### 3. Test Login Endpoint

```bash
curl -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@villagebank.com","password":"admin123"}'
```

Should return a JWT token.

### 4. Test /me Endpoint

```bash
# Get token first
TOKEN=$(curl -s -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@villagebank.com","password":"admin123"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Test /me endpoint
curl -X GET http://localhost:8002/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Origin: http://localhost:3000"
```

Should return user data, not a 500 error.

### 5. Clear Browser Cache

- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows/Linux)
- Or clear browser cache completely

### 6. Check Browser Console

Look for:
- CORS errors
- Network errors
- 500 Internal Server Error

### 7. Check Backend Logs

The uvicorn server should show error traces if there's a 500 error. Look for Python tracebacks in the terminal where the server is running.

## Common Fixes Applied

1. ✅ Fixed UUID serialization in UserResponse
2. ✅ Fixed CORS configuration
3. ✅ Fixed password hashing (bcrypt direct)
4. ✅ Fixed UUID conversion in get_current_user

## If Still Not Working

1. Check if backend server is actually running on port 8002
2. Check if there are any Python errors in the backend terminal
3. Verify the database connection is working
4. Try accessing the API docs: http://localhost:8002/docs
