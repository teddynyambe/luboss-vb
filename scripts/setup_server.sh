#!/bin/bash

# Luboss95 Village Banking v2 - Initial Server Setup Script
# This script sets up the server for the first time
# Run this on the server: bash <(curl -s script-url) or copy and run

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root or with sudo"
    exit 1
fi

print_info "Starting Luboss95 Village Banking v2 server setup..."

# Detect Linux distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VER=$VERSION_ID
else
    print_error "Cannot detect Linux distribution"
    exit 1
fi

print_info "Detected OS: $OS $VER"

# Update package list
print_info "Updating package list..."
apt-get update -qq

# Install system dependencies
print_info "Installing system dependencies..."

# Python 3.11+
if ! command -v python3.11 &> /dev/null && ! command -v python3.12 &> /dev/null; then
    print_info "Installing Python 3.11+..."
    apt-get install -y software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip
    print_success "Python 3.11+ installed"
else
    print_success "Python 3.11+ already installed"
fi

# Node.js 18+
if ! command -v node &> /dev/null || [ "$(node -v | cut -d'v' -f2 | cut -d'.' -f1)" -lt 18 ]; then
    print_info "Installing Node.js 18+..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y nodejs
    print_success "Node.js installed: $(node -v)"
else
    print_success "Node.js already installed: $(node -v)"
fi

# PostgreSQL (check if installed)
if ! command -v psql &> /dev/null; then
    print_warning "PostgreSQL not found. Please install PostgreSQL 17+ manually."
    print_info "Install with: apt-get install -y postgresql-17 postgresql-contrib-17"
else
    print_success "PostgreSQL found: $(psql --version)"
fi

# Check for existing Nginx
if command -v nginx &> /dev/null; then
    print_success "Nginx already installed: $(nginx -v 2>&1)"
    NGINX_EXISTS=true
else
    print_warning "Nginx not found. Please install Nginx manually if needed."
    print_info "Install with: apt-get install -y nginx"
    NGINX_EXISTS=false
fi

# Check for SSL certificates
if [ -d "/etc/letsencrypt/live" ]; then
    print_success "Let's Encrypt certificates found"
    SSL_EXISTS=true
else
    print_warning "SSL certificates not found in /etc/letsencrypt/live"
    print_info "SSL certificates should be configured separately"
    SSL_EXISTS=false
fi

# Create deployment directory
DEPLOY_DIR="/var/www/luboss-vb"
print_info "Creating deployment directory: $DEPLOY_DIR"
mkdir -p $DEPLOY_DIR
chown -R www-data:www-data $DEPLOY_DIR

# Create Python virtual environment
print_info "Setting up Python virtual environment..."
if [ ! -d "$DEPLOY_DIR/app/venv" ]; then
    python3.11 -m venv $DEPLOY_DIR/app/venv
    print_success "Virtual environment created"
else
    print_success "Virtual environment already exists"
fi

# Install Python dependencies
print_info "Installing Python dependencies..."
source $DEPLOY_DIR/app/venv/bin/activate
pip install --upgrade pip
if [ -f "$DEPLOY_DIR/app/requirements.txt" ]; then
    pip install -r $DEPLOY_DIR/app/requirements.txt
    print_success "Python dependencies installed"
else
    print_warning "requirements.txt not found. Will be installed during first deployment."
fi

# Install Node.js dependencies (if package.json exists)
if [ -f "$DEPLOY_DIR/ui/package.json" ]; then
    print_info "Installing Node.js dependencies..."
    cd $DEPLOY_DIR/ui
    npm ci --production
    print_success "Node.js dependencies installed"
else
    print_warning "package.json not found. Will be installed during first deployment."
fi

# Create systemd service files
print_info "Setting up systemd services..."

# Backend service
if [ -f "$DEPLOY_DIR/deploy/luboss-backend.service" ]; then
    cp $DEPLOY_DIR/deploy/luboss-backend.service /etc/systemd/system/
    systemctl daemon-reload
    print_success "Backend service file installed"
else
    print_warning "Backend service file not found. Will be created during deployment."
fi

# Frontend service
if [ -f "$DEPLOY_DIR/deploy/luboss-frontend.service" ]; then
    cp $DEPLOY_DIR/deploy/luboss-frontend.service /etc/systemd/system/
    systemctl daemon-reload
    print_success "Frontend service file installed"
else
    print_warning "Frontend service file not found. Will be created during deployment."
fi

# Setup Nginx configuration (if Nginx exists)
if [ "$NGINX_EXISTS" = true ]; then
    print_info "Setting up Nginx configuration..."
    
    if [ -f "$DEPLOY_DIR/deploy/nginx-luboss.conf" ]; then
        # Note: This is a location block, needs to be included in main server block
        cp $DEPLOY_DIR/deploy/nginx-luboss.conf /etc/nginx/sites-available/luboss-vb
        print_success "Nginx configuration copied to sites-available"
        print_warning "You need to manually include this in your main server block or create a symlink"
        print_info "To enable: ln -s /etc/nginx/sites-available/luboss-vb /etc/nginx/sites-enabled/"
        print_info "Then test: nginx -t && systemctl reload nginx"
    else
        print_warning "Nginx configuration file not found. Will be created during deployment."
    fi
fi

# Create environment file templates
print_info "Setting up environment file templates..."

if [ -f "$DEPLOY_DIR/deploy/env.backend.template" ]; then
    if [ ! -f "$DEPLOY_DIR/app/.env.production" ]; then
        cp $DEPLOY_DIR/deploy/env.backend.template $DEPLOY_DIR/app/.env.production
        print_success "Backend .env.production template created"
        print_warning "Please edit $DEPLOY_DIR/app/.env.production with actual values"
    else
        print_success "Backend .env.production already exists"
    fi
fi

if [ -f "$DEPLOY_DIR/deploy/env.frontend.template" ]; then
    if [ ! -f "$DEPLOY_DIR/ui/.env.production" ]; then
        cp $DEPLOY_DIR/deploy/env.frontend.template $DEPLOY_DIR/ui/.env.production
        print_success "Frontend .env.production template created"
        print_warning "Please edit $DEPLOY_DIR/ui/.env.production with actual values"
    else
        print_success "Frontend .env.production already exists"
    fi
fi

# Set permissions
print_info "Setting file permissions..."
chown -R www-data:www-data $DEPLOY_DIR
chmod -R 755 $DEPLOY_DIR

print_success "Server setup completed!"
print_info ""
print_info "Next steps:"
print_info "1. Edit $DEPLOY_DIR/app/.env.production with database and API keys"
print_info "2. Edit $DEPLOY_DIR/ui/.env.production with API URL"
print_info "3. Configure Nginx to include the luboss-vb configuration"
print_info "4. Run database migrations: cd $DEPLOY_DIR && source app/venv/bin/activate && alembic upgrade head"
print_info "5. Start services: systemctl start luboss-backend luboss-frontend"
print_info "6. Enable services: systemctl enable luboss-backend luboss-frontend"
