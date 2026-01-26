# Nginx Configuration Example

## Your Current Config (lubossvb.conf)

Add the include directive inside the HTTPS server block, after all existing location blocks.

## Updated Configuration

```nginx
# Redirect all HTTP traffic to HTTPS
server {
    listen 80;
    server_name lubossvb.com www.lubossvb.com;

    # Redirect all HTTP requests to HTTPS
    return 301 https://$host$request_uri;
}

# Handle HTTPS traffic
server {
    listen 443 ssl;

    server_name lubossvb.com www.lubossvb.com;

    # Specify the locations of your SSL certificate and key files
    ssl_certificate /etc/ssl/luboss/certificate.crt;
    ssl_certificate_key /etc/ssl/luboss/private.key;

    # Recommended SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Location for ACME Challenge
    location ~ ^/.well-known/pki-validation/ {
        root /var/www/html;
        try_files $uri $uri/ =404;
    }

    # Logging
    access_log /var/log/nginx/lubossvb.com_access.log;
    error_log /var/log/nginx/lubossvb.com_error.log;

    # --- API (Flask + Gunicorn socket) ---
    location /api {
        include proxy_params;
        proxy_pass http://unix:/var/apps/luboss_api/luboss_api.sock;
    }

    # --- Static Frontend (React Build) ---
    location / {
        root /var/www/html/luboss_ui;
        index index.html;
        try_files $uri /index.html;
        error_page 404 /index.html;
    }

    # --- Uploads (if still needed) ---
    location /uploads/ {
        alias /var/apps/luboss_api/uploads/;
    }

    # ⬇️ ADD THIS LINE HERE (after all location blocks, inside server block):
    include /etc/nginx/sites-available/luboss-vb;
}
```

## What to Do

1. **Edit the file:**
   ```bash
   sudo vi /etc/nginx/sites-available/lubossvb.conf
   ```

2. **Add this line** at the end of the HTTPS server block (after `location /uploads/`):
   ```nginx
   include /etc/nginx/sites-available/luboss-vb;
   ```

3. **Save and exit** (in vi: press `Esc`, then type `:wq` and press Enter)

4. **Test the configuration:**
   ```bash
   sudo nginx -t
   ```

5. **If test passes, reload Nginx:**
   ```bash
   sudo systemctl reload nginx
   ```

6. **Verify it works:**
   ```bash
   curl -I https://lubossvb.com/test
   # Should return 200 OK, not a redirect
   ```

## Important Notes

- The include must be **inside** the `server { }` block
- It should be **after** all existing `location` blocks
- It should be **before** the closing `}` of the server block
- The path `/etc/nginx/sites-available/luboss-vb` must exist (it was created by the deployment script)

## What This Does

The included file (`luboss-vb`) contains location blocks for:
- `/test` → Next.js frontend on port 3000
- `/test/api` → FastAPI backend on port 8002
- `/test/_next/static` → Static assets from Next.js

These location blocks will be processed **after** the existing `/api` and `/` locations, so:
- `/api` → Still goes to your Flask/Gunicorn socket (production)
- `/` → Still serves your React build (production)
- `/test` → Goes to Next.js frontend (new deployment)
- `/test/api` → Goes to FastAPI backend (new deployment)

## Troubleshooting

If you get an error when testing:

1. **"location directive is not allowed here"**
   - The include is outside the server block
   - Make sure it's inside the `server { }` block

2. **"file not found"**
   - Check the file exists: `sudo ls -la /etc/nginx/sites-available/luboss-vb`
   - Verify the path is correct

3. **Still redirecting to /login**
   - Check if services are running: `sudo systemctl status luboss-frontend luboss-backend`
   - Check if ports are listening: `sudo lsof -i:3000` and `sudo lsof -i:8002`
   - Check Nginx error log: `sudo tail -f /var/log/nginx/error.log`
