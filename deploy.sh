#!/bin/bash

# Luboss95 Village Banking v2 - Deployment Script
# This script deploys the application to a Linux server
# Usage: ./deploy.sh [--dry-run]

set -e  # Exit on error

# Parse command line arguments
DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    set +e  # Don't exit on error in dry-run mode
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Check if deploy.conf exists
if [ ! -f "deploy.conf" ]; then
    print_error "deploy.conf not found!"
    print_info "Please copy deploy.conf.example to deploy.conf and configure it:"
    echo "  cp deploy.conf.example deploy.conf"
    echo "  # Then edit deploy.conf with your server details"
    exit 1
fi

# Load configuration
source deploy.conf

# Validate required variables
if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_USER" ] || [ -z "$DEPLOY_DIR" ]; then
    print_error "Missing required configuration in deploy.conf"
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    print_info "DRY RUN MODE: Starting deployment analysis for ${SERVER_USER}@${SERVER_HOST}"
else
    print_info "Starting deployment to ${SERVER_USER}@${SERVER_HOST}"
fi

# Check for uncommitted changes (skip in dry-run mode)
if [ "$DRY_RUN" = false ]; then
    if [ -n "$(git status --porcelain)" ]; then
        print_warning "You have uncommitted changes. Consider committing them first."
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Check if sshpass is available (for password authentication)
USE_SSHPASS=false
if command -v sshpass &> /dev/null; then
    if [ -n "$SSH_PASSWORD" ]; then
        USE_SSHPASS=true
        SSH_CMD="sshpass -p '${SSH_PASSWORD}' ssh"
        SCP_CMD="sshpass -p '${SSH_PASSWORD}' scp"
    fi
fi

if [ "$USE_SSHPASS" = false ]; then
    SSH_CMD="ssh"
    SCP_CMD="scp"
    if [ -n "$SSH_PASSWORD" ]; then
        print_warning "sshpass not found. Using SSH key authentication."
        print_info "Install sshpass for password authentication: brew install sshpass (macOS) or apt-get install sshpass (Linux)"
    fi
fi

# SSH options with connection multiplexing to reduce password prompts
SSH_CONTROL_DIR="$HOME/.ssh/controlmasters"
mkdir -p "$SSH_CONTROL_DIR" 2>/dev/null || true
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
SSH_OPTS="${SSH_OPTS} -o ControlMaster=auto -o ControlPath=${SSH_CONTROL_DIR}/%r@%h:%p -o ControlPersist=300"
if [ -n "$SSH_PORT" ]; then
    SSH_OPTS="${SSH_OPTS} -p ${SSH_PORT}"
fi

SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

# Test SSH connection
print_info "Testing SSH connection..."
if ! $SSH_CMD $SSH_OPTS $SSH_TARGET "echo 'Connection successful'" &> /dev/null; then
    print_error "Failed to connect to server. Please check your SSH configuration."
    if [ "$DRY_RUN" = false ]; then
        exit 1
    else
        print_warning "Continuing in dry-run mode despite connection failure..."
    fi
else
    print_success "SSH connection successful"
fi

# Function to execute remote command
remote_exec() {
    if [ "$USE_SSHPASS" = true ]; then
        sshpass -p "${SSH_PASSWORD}" ssh $SSH_OPTS $SSH_TARGET "$1"
    else
        ssh $SSH_OPTS $SSH_TARGET "$1"
    fi
}

# Function to execute remote command with sudo (tries without sudo first)
remote_exec_sudo() {
    local cmd=$1
    # Try without sudo first
    if remote_exec "$cmd" 2>/dev/null; then
        return 0
    fi
    # If that fails, try with sudo -n (non-interactive, fails if password needed)
    if remote_exec "sudo -n $cmd" 2>/dev/null; then
        return 0
    fi
    # If sudo -n fails, we need password - but this will still prompt
    # Note: For better experience, configure passwordless sudo on server:
    # echo "${SERVER_USER} ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /usr/sbin/nginx" | sudo tee /etc/sudoers.d/luboss-deploy
    print_warning "Sudo command requires password. Consider setting up passwordless sudo for deployment."
    remote_exec "sudo $cmd"
}

# Function to copy file to server
remote_copy() {
    local src=$1
    local dest=$2
    if [ "$USE_SSHPASS" = true ]; then
        sshpass -p "${SSH_PASSWORD}" scp $SSH_OPTS "$src" "${SSH_TARGET}:${dest}"
    else
        scp $SSH_OPTS "$src" "${SSH_TARGET}:${dest}"
    fi
}

# Function to check if a port is available on remote server
check_port_available() {
    local port=$1
    local result=$(remote_exec "lsof -i:${port} 2>/dev/null | grep LISTEN || echo 'available'")
    if echo "$result" | grep -q "LISTEN"; then
        return 1  # Port is in use
    else
        return 0  # Port is available
    fi
}

# Verify required ports are available
verify_ports() {
    print_info "Verifying required ports are available..."
    
    if ! check_port_available "${BACKEND_PORT}"; then
        print_error "Port ${BACKEND_PORT} is already in use!"
        print_info "Please free port ${BACKEND_PORT} or change BACKEND_PORT in deploy.conf"
        if [ "$DRY_RUN" = false ]; then
            exit 1
        else
            print_warning "Continuing in dry-run mode..."
        fi
    else
        print_success "Port ${BACKEND_PORT} is available"
    fi
    
    if ! check_port_available "${FRONTEND_PORT}"; then
        print_error "Port ${FRONTEND_PORT} is already in use!"
        print_info "Please free port ${FRONTEND_PORT} or change FRONTEND_PORT in deploy.conf"
        if [ "$DRY_RUN" = false ]; then
            exit 1
        else
            print_warning "Continuing in dry-run mode..."
        fi
    else
        print_success "Port ${FRONTEND_PORT} is available"
    fi
}

# Verify ports are available after SSH connection is established
verify_ports

# Helper function to get current git commit hash (local)
get_local_git_commit() {
    git rev-parse HEAD 2>/dev/null || echo "unknown"
}

# Helper function to get current git commit hash (remote)
get_remote_git_commit() {
    remote_exec "cd ${DEPLOY_DIR} && git rev-parse HEAD 2>/dev/null || echo 'unknown'"
}

# Helper function to get git commits since a specific commit
get_git_commits_since() {
    local since_commit=$1
    remote_exec "cd ${DEPLOY_DIR} && git log --oneline ${since_commit}..HEAD 2>/dev/null | head -20"
}

# Helper function to get file hash (SHA256) on remote server
get_remote_file_hash() {
    local file_path=$1
    remote_exec "if [ -f '${file_path}' ]; then sha256sum '${file_path}' 2>/dev/null | cut -d' ' -f1; else echo 'FILE_NOT_FOUND'; fi"
}

# Helper function to get current database migration version
get_current_migration_version() {
    remote_exec "cd ${DEPLOY_DIR} && source app/venv/bin/activate && alembic current 2>/dev/null | grep -oP '^\w+' | head -1 || echo 'unknown'"
}

# Helper function to get pending migrations
get_pending_migrations() {
    remote_exec "cd ${DEPLOY_DIR} && source app/venv/bin/activate && alembic heads 2>/dev/null | head -1"
}

# Helper function to get service status
get_service_status() {
    local service_name=$1
    # Try without sudo first (if user has permissions)
    remote_exec "systemctl is-active ${service_name} 2>/dev/null || sudo -n systemctl is-active ${service_name} 2>/dev/null || echo 'inactive'"
}

# Helper function to get package-lock.json hash
get_package_lock_hash() {
    remote_exec "if [ -f '${DEPLOY_DIR}/ui/package-lock.json' ]; then sha256sum '${DEPLOY_DIR}/ui/package-lock.json' 2>/dev/null | cut -d' ' -f1; else echo 'FILE_NOT_FOUND'; fi"
}

# Helper function to get pip freeze hash
get_pip_freeze_hash() {
    remote_exec "cd ${DEPLOY_DIR}/app && venv/bin/pip freeze 2>/dev/null | sha256sum | cut -d' ' -f1 || echo 'unknown'"
}

# Function to extract JSON value (portable method)
extract_json_value() {
    local json=$1
    local key=$2
    echo "$json" | sed -n "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"
}

# Function to load deployment log from server
load_deployment_log() {
    local log_content
    log_content=$(remote_exec "cat ${DEPLOY_DIR}/.deployment.log 2>/dev/null" || echo "")
    
    if [ -z "$log_content" ] || [ "$log_content" = "" ]; then
        return 1  # Log file doesn't exist
    fi
    
    # Parse JSON log (portable method using sed)
    LAST_DEPLOY_TIMESTAMP=$(extract_json_value "$log_content" "timestamp")
    LAST_DEPLOY_COMMIT=$(extract_json_value "$log_content" "git_commit")
    LAST_DEPLOY_BRANCH=$(extract_json_value "$log_content" "git_branch")
    LAST_FRONTEND_ENV_HASH=$(extract_json_value "$log_content" "frontend_env_hash")
    LAST_BACKEND_ENV_HASH=$(extract_json_value "$log_content" "backend_env_hash")
    LAST_NEXT_CONFIG_HASH=$(extract_json_value "$log_content" "next_config_hash")
    LAST_NGINX_CONFIG_HASH=$(extract_json_value "$log_content" "nginx_config_hash")
    LAST_MIGRATION_VERSION=$(extract_json_value "$log_content" "migration_version")
    LAST_PIP_FREEZE_HASH=$(extract_json_value "$log_content" "pip_freeze_hash")
    LAST_PACKAGE_LOCK_HASH=$(extract_json_value "$log_content" "package_lock_hash")
    LAST_BACKEND_SERVICE_STATUS=$(extract_json_value "$log_content" "backend_service_status")
    LAST_FRONTEND_SERVICE_STATUS=$(extract_json_value "$log_content" "frontend_service_status")
    
    return 0
}

# Function to create deployment log on server
create_deployment_log() {
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local git_commit=$(get_remote_git_commit)
    local git_branch=$(remote_exec "cd ${DEPLOY_DIR} && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown'")
    local deployer="${USER}@$(hostname)"
    
    local frontend_env_hash=$(get_remote_file_hash "${DEPLOY_DIR}/ui/.env.production")
    local backend_env_hash=$(get_remote_file_hash "${DEPLOY_DIR}/app/.env.production")
    local next_config_hash=$(get_remote_file_hash "${DEPLOY_DIR}/ui/next.config.ts")
    local nginx_config_hash="FILE_NOT_FOUND"
    if [ -n "${NGINX_SITES_AVAILABLE}" ] && [ -n "${NGINX_SITE_NAME}" ]; then
        nginx_config_hash=$(get_remote_file_hash "${NGINX_SITES_AVAILABLE}/${NGINX_SITE_NAME}")
    fi
    local migration_version=$(get_current_migration_version)
    local pip_freeze_hash=$(get_pip_freeze_hash)
    local package_lock_hash=$(get_package_lock_hash)
    local backend_service_status=$(get_service_status "${BACKEND_SERVICE_NAME}")
    local frontend_service_status=$(get_service_status "${FRONTEND_SERVICE_NAME}")
    
    # Create JSON log
    local log_json=$(cat <<EOF
{
  "timestamp": "${timestamp}",
  "git_commit": "${git_commit}",
  "git_branch": "${git_branch}",
  "deployer": "${deployer}",
  "frontend_env_hash": "${frontend_env_hash}",
  "backend_env_hash": "${backend_env_hash}",
  "next_config_hash": "${next_config_hash}",
  "nginx_config_hash": "${nginx_config_hash}",
  "migration_version": "${migration_version}",
  "pip_freeze_hash": "${pip_freeze_hash}",
  "package_lock_hash": "${package_lock_hash}",
  "backend_service_status": "${backend_service_status}",
  "frontend_service_status": "${frontend_service_status}"
}
EOF
)
    
    # Backup old log (keep last 5)
    remote_exec "cd ${DEPLOY_DIR} && \
        if [ -f .deployment.log.4 ]; then rm -f .deployment.log.5; fi && \
        if [ -f .deployment.log.3 ]; then mv .deployment.log.4 .deployment.log.5; fi && \
        if [ -f .deployment.log.2 ]; then mv .deployment.log.3 .deployment.log.4; fi && \
        if [ -f .deployment.log.1 ]; then mv .deployment.log.2 .deployment.log.3; fi && \
        if [ -f .deployment.log ]; then mv .deployment.log .deployment.log.1; fi"
    
    # Write new log
    echo "$log_json" | remote_exec "cat > ${DEPLOY_DIR}/.deployment.log"
}

# Function to compare states and display changes
compare_states() {
    local first_deployment=$1
    
    echo ""
    echo "=== DRY RUN: Deployment Preview ==="
    echo ""
    
    if [ "$first_deployment" = true ]; then
        echo -e "${YELLOW}Deployment Type: FIRST DEPLOYMENT${NC}"
        echo ""
        echo "This appears to be the first deployment. The following initial setup will be performed:"
        echo ""
        echo "  ${GREEN}✓${NC} Database setup and migrations"
        echo "  ${GREEN}✓${NC} Service installation and configuration"
        echo "  ${GREEN}✓${NC} Nginx configuration"
        echo "  ${GREEN}✓${NC} Initial frontend build"
        echo "  ${GREEN}✓${NC} Service startup"
        echo ""
    else
        echo -e "${BLUE}Deployment Type: UPDATE${NC}"
        echo ""
        echo "Last deployment: ${LAST_DEPLOY_TIMESTAMP}"
        echo "Last commit: ${LAST_DEPLOY_COMMIT}"
        echo ""
        
        # Code changes
        local current_commit=$(get_remote_git_commit)
        if [ "$current_commit" != "$LAST_DEPLOY_COMMIT" ] && [ "$current_commit" != "unknown" ] && [ "$LAST_DEPLOY_COMMIT" != "unknown" ]; then
            local commits=$(get_git_commits_since "$LAST_DEPLOY_COMMIT")
            local commit_count=0
            if [ -n "$commits" ]; then
                commit_count=$(echo "$commits" | grep -v '^$' | wc -l | tr -d ' ')
            fi
            if [ "$commit_count" -gt 0 ]; then
                echo -e "${GREEN}Code Changes:${NC}"
                echo -e "  ${GREEN}✓${NC} ${commit_count} new commit(s) since last deployment"
                echo "$commits" | while IFS= read -r line; do
                    if [ -n "$line" ]; then
                        echo "  - $line"
                    fi
                done
                echo ""
            else
                echo -e "${GREEN}Code Changes:${NC}"
                echo -e "  ${GREEN}✓${NC} Code will be updated (git pull)"
                echo ""
            fi
        else
            echo -e "${BLUE}Code Changes:${NC}"
            echo -e "  ${BLUE}✓${NC} No new commits"
            echo ""
        fi
        
        # Configuration changes
        echo -e "${BLUE}Configuration Changes:${NC}"
        local current_frontend_env=$(get_remote_file_hash "${DEPLOY_DIR}/ui/.env.production")
        if [ "$current_frontend_env" != "$LAST_FRONTEND_ENV_HASH" ] && [ "$current_frontend_env" != "FILE_NOT_FOUND" ]; then
            echo -e "  ${YELLOW}⚠${NC}  Frontend .env.production changed"
        else
            echo -e "  ${GREEN}✓${NC}  Frontend .env.production unchanged"
        fi
        
        local current_backend_env=$(get_remote_file_hash "${DEPLOY_DIR}/app/.env.production")
        if [ "$current_backend_env" != "$LAST_BACKEND_ENV_HASH" ] && [ "$current_backend_env" != "FILE_NOT_FOUND" ]; then
            echo -e "  ${YELLOW}⚠${NC}  Backend .env.production changed"
        else
            echo -e "  ${GREEN}✓${NC}  Backend .env.production unchanged"
        fi
        
        local current_next_config=$(get_remote_file_hash "${DEPLOY_DIR}/ui/next.config.ts")
        if [ "$current_next_config" != "$LAST_NEXT_CONFIG_HASH" ] && [ "$current_next_config" != "FILE_NOT_FOUND" ]; then
            echo -e "  ${YELLOW}⚠${NC}  next.config.ts changed"
        else
            echo -e "  ${GREEN}✓${NC}  next.config.ts unchanged"
        fi
        
        local current_nginx_config="FILE_NOT_FOUND"
        if [ -n "${NGINX_SITES_AVAILABLE}" ] && [ -n "${NGINX_SITE_NAME}" ]; then
            current_nginx_config=$(get_remote_file_hash "${NGINX_SITES_AVAILABLE}/${NGINX_SITE_NAME}")
        fi
        if [ "$current_nginx_config" != "$LAST_NGINX_CONFIG_HASH" ] && [ "$current_nginx_config" != "FILE_NOT_FOUND" ]; then
            echo -e "  ${YELLOW}⚠${NC}  Nginx configuration changed"
        else
            echo -e "  ${GREEN}✓${NC}  Nginx configuration unchanged"
        fi
        echo ""
        
        # Database changes
        local current_migration=$(get_current_migration_version)
        local head_migration=$(get_pending_migrations)
        if [ "$current_migration" != "$head_migration" ] && [ "$head_migration" != "unknown" ] && [ "$head_migration" != "" ]; then
            echo -e "${GREEN}Database Changes:${NC}"
            echo -e "  ${GREEN}✓${NC}  Migration version: ${current_migration} -> ${head_migration}"
            echo -e "  ${GREEN}✓${NC}  Pending migrations will be applied"
        elif [ "$current_migration" != "$LAST_MIGRATION_VERSION" ]; then
            echo -e "${YELLOW}Database Changes:${NC}"
            echo -e "  ${YELLOW}⚠${NC}  Migration version may have changed"
        else
            echo -e "${BLUE}Database Changes:${NC}"
            echo -e "  ${BLUE}✓${NC}  No pending migrations"
        fi
        echo ""
        
        # Dependency updates
        echo -e "${BLUE}Dependency Updates:${NC}"
        local current_pip_hash=$(get_pip_freeze_hash)
        if [ "$current_pip_hash" != "$LAST_PIP_FREEZE_HASH" ]; then
            echo -e "  ${YELLOW}⚠${NC}  Python packages updated (pip freeze hash changed)"
        else
            echo -e "  ${GREEN}✓${NC}  Python packages unchanged"
        fi
        
        local current_package_lock=$(get_package_lock_hash)
        if [ "$current_package_lock" != "$LAST_PACKAGE_LOCK_HASH" ] && [ "$current_package_lock" != "FILE_NOT_FOUND" ]; then
            echo -e "  ${YELLOW}⚠${NC}  npm packages updated (package-lock.json changed)"
        else
            echo -e "  ${GREEN}✓${NC}  npm packages unchanged"
        fi
        echo ""
        
        # Service actions
        echo -e "${BLUE}Service Actions:${NC}"
        local current_backend_status=$(get_service_status "${BACKEND_SERVICE_NAME}")
        if [ "$current_backend_status" != "active" ]; then
            echo -e "  ${YELLOW}⚠${NC}  Backend service: ${current_backend_status} (will start)"
        else
            echo -e "  ${GREEN}✓${NC}  Backend service: restart required"
        fi
        
        local current_frontend_status=$(get_service_status "${FRONTEND_SERVICE_NAME}")
        if [ "$current_frontend_status" != "active" ]; then
            echo -e "  ${YELLOW}⚠${NC}  Frontend service: ${current_frontend_status} (will start)"
        else
            echo -e "  ${GREEN}✓${NC}  Frontend service: restart required"
        fi
        
        echo -e "  ${GREEN}✓${NC}  Nginx: reload required"
        echo ""
    fi
    
    # Estimated actions
    echo -e "${BLUE}Estimated Actions:${NC}"
    echo "  - git pull"
    if [ "$first_deployment" = true ] || [ "$current_migration" != "$head_migration" ]; then
        echo "  - Run database migrations"
    fi
    if [ "$first_deployment" = true ] || [ "$current_pip_hash" != "$LAST_PIP_FREEZE_HASH" ]; then
        echo "  - Update Python dependencies"
    fi
    if [ "$first_deployment" = true ] || [ "$current_package_lock" != "$LAST_PACKAGE_LOCK_HASH" ]; then
        echo "  - Update npm dependencies"
        echo "  - Build frontend"
    fi
    if [ "$first_deployment" = true ] || [ "$current_nginx_config" != "$LAST_NGINX_CONFIG_HASH" ]; then
        echo "  - Update Nginx configuration"
        echo "  - Reload Nginx"
    fi
    echo "  - Restart backend service"
    echo "  - Restart frontend service"
    echo ""
    echo "=== End of Dry Run ==="
    echo ""
}

# Function to perform dry-run deployment
dry_run_deploy() {
    print_info "DRY RUN MODE: Analyzing deployment changes..."
    print_info "No changes will be made to the server."
    echo ""
    
    # Check if deployment log exists
    if ! load_deployment_log; then
        print_warning "No deployment log found. This appears to be a first deployment."
        compare_states true
    else
        print_info "Found previous deployment log from ${LAST_DEPLOY_TIMESTAMP}"
        compare_states false
    fi
    
    print_success "Dry-run completed. Run without --dry-run to perform actual deployment."
}

# Deploy function
deploy() {
    print_info "Deploying to ${DEPLOY_DIR}..."
    
    # 0. Check if deployment directory exists, create and clone if needed
    if ! remote_exec "test -d ${DEPLOY_DIR}" 2>/dev/null; then
        print_info "Deployment directory does not exist. Setting up for first deployment..."
        
        # Get git repository URL (from config or auto-detect from local repo)
        local repo_url="${GIT_REPO_URL}"
        if [ -z "$repo_url" ]; then
            print_info "GIT_REPO_URL not set, attempting to detect from local repository..."
            repo_url=$(git remote get-url origin 2>/dev/null || echo "")
            if [ -z "$repo_url" ]; then
                print_error "Cannot determine git repository URL."
                print_info "Please set GIT_REPO_URL in deploy.conf or ensure local repository has 'origin' remote."
                exit 1
            fi
            print_info "Detected repository URL: ${repo_url}"
            
            # If HTTPS URL detected and might be private, suggest SSH
            if echo "$repo_url" | grep -q "^https://"; then
                print_info "Note: Using HTTPS URL. If repository is private, consider using SSH URL:"
                local ssh_url=$(echo "$repo_url" | sed 's|https://github.com/|git@github.com:|' | sed 's|\.git$||')
                print_info "  GIT_REPO_URL=${ssh_url}.git"
            fi
        fi
        
        # Create parent directory (try without sudo first)
        print_info "Creating deployment directory..."
        local parent_dir=$(dirname ${DEPLOY_DIR})
        if ! remote_exec "mkdir -p ${parent_dir}" 2>/dev/null; then
            print_info "Directory creation requires sudo privileges..."
            # Try to create with sudo, but if it fails, provide instructions
            if ! remote_exec "sudo -n mkdir -p ${parent_dir}" 2>/dev/null; then
                print_error "Cannot create directory ${parent_dir} without sudo password."
                print_info "Please run this command manually on the server:"
                echo "  sudo mkdir -p ${parent_dir}"
                echo "  sudo chown ${SERVER_USER}:${SERVER_USER} ${parent_dir}"
                exit 1
            fi
        fi
        
        # Clone repository to a temporary location first (user-writable)
        print_info "Cloning repository from ${repo_url}..."
        # Get remote user's home directory
        local remote_home=$(remote_exec "echo \$HOME")
        local temp_dir="${remote_home}/luboss-vb-temp-$$"
        
        # Check if git is installed
        if ! remote_exec "command -v git" >/dev/null 2>&1; then
            print_error "Git is not installed on the server."
            print_info "Please install git: sudo apt-get install git (Ubuntu/Debian) or sudo yum install git (CentOS/RHEL)"
            exit 1
        fi
        
        # Clone to user's home directory first (show errors for debugging)
        print_info "Attempting to clone repository..."
        local clone_output=$(remote_exec "git clone -b ${GIT_BRANCH:-main} ${repo_url} ${temp_dir} 2>&1")
        local clone_exit=$?
        
        if [ $clone_exit -ne 0 ]; then
            print_error "Failed to clone repository."
            echo "Git output: $clone_output"
            print_info ""
            print_info "Possible issues:"
            print_info "  1. Repository is private and requires authentication"
            print_info "  2. Network connectivity issues on server"
            print_info "  3. Branch '${GIT_BRANCH:-main}' doesn't exist"
            print_info ""
            print_info "Solutions:"
            print_info "  - If repository is private, set up SSH keys on server:"
            print_info "    ssh-keygen -t rsa -b 4096 -C 'deploy@server'"
            print_info "    cat ~/.ssh/id_rsa.pub  # Add to GitHub SSH keys"
            print_info "  - Or use SSH URL instead: git@github.com:teddynyambe/luboss-vb.git"
            print_info "  - Or clone manually on server first, then run deploy script again"
            exit 1
        fi
        
        print_success "Repository cloned successfully"
        
        # Move to final location (may require sudo)
        print_info "Moving repository to ${DEPLOY_DIR}..."
        if ! remote_exec "mv ${temp_dir} ${DEPLOY_DIR}" 2>/dev/null; then
            # Try with sudo
            if remote_exec "sudo -n mv ${temp_dir} ${DEPLOY_DIR}" 2>/dev/null; then
                remote_exec "sudo -n chown -R ${SERVER_USER}:${SERVER_USER} ${DEPLOY_DIR}"
                print_success "Repository moved to ${DEPLOY_DIR}"
            else
                print_error "Cannot move repository to ${DEPLOY_DIR} without sudo password."
                print_info "The repository has been cloned to: ${temp_dir}"
                print_info "Please run these commands manually on the server:"
                echo "  sudo mv ${temp_dir} ${DEPLOY_DIR}"
                echo "  sudo chown -R ${SERVER_USER}:${SERVER_USER} ${DEPLOY_DIR}"
                print_info "Then run ./deploy.sh again to continue deployment."
                exit 1
            fi
        else
            print_success "Repository moved to ${DEPLOY_DIR}"
        fi
        print_success "Repository cloned"
    elif ! remote_exec "test -d ${DEPLOY_DIR}/.git" 2>/dev/null; then
        print_warning "Directory exists but is not a git repository."
        print_info "Attempting to initialize git repository..."
        
        # Get git repository URL
        local repo_url="${GIT_REPO_URL}"
        if [ -z "$repo_url" ]; then
            repo_url=$(git remote get-url origin 2>/dev/null || echo "")
            if [ -z "$repo_url" ]; then
                print_error "Cannot determine git repository URL."
                print_info "Please set GIT_REPO_URL in deploy.conf."
                exit 1
            fi
        fi
        
        remote_exec "cd ${DEPLOY_DIR} && git init && git remote add origin ${repo_url} && git fetch && git checkout -b ${GIT_BRANCH:-main} origin/${GIT_BRANCH:-main} || git checkout ${GIT_BRANCH:-main}"
        print_success "Git repository initialized"
    fi
    
    # 1. Pull latest code
    print_info "Pulling latest code from git..."
    remote_exec "cd ${DEPLOY_DIR} && git pull origin ${GIT_BRANCH:-main}"
    print_success "Code updated"
    
    # 2. Update Next.js config with basePath via environment variable
    print_info "Updating Next.js configuration for ${DEPLOY_PATH} deployment..."
    # The next.config.ts already reads from NEXT_PUBLIC_BASE_PATH, so we set it during build
    print_success "Next.js will use basePath from environment variable"
    
    # 3. Update backend environment (if .env.production exists, update it)
    print_info "Checking backend environment..."
    remote_exec "cd ${DEPLOY_DIR} && if [ -f app/.env.production ]; then echo 'Backend .env.production exists'; else echo 'Backend .env.production not found - using app/.env'; fi"
    
    # 4. Update frontend environment
    print_info "Updating frontend environment..."
    remote_exec "cd ${DEPLOY_DIR}/ui && cat > .env.production << EOF
NEXT_PUBLIC_BASE_PATH=${DEPLOY_PATH}
NEXT_PUBLIC_API_URL=https://${DOMAIN}${DEPLOY_PATH}/api
EOF"
    print_success "Frontend environment updated"
    
    # 4.5. Setup Python virtual environment if it doesn't exist
    print_info "Checking Python virtual environment..."
    if ! remote_exec "test -d ${DEPLOY_DIR}/app/venv" 2>/dev/null; then
        print_info "Virtual environment not found. Creating it..."
        
        # Find Python 3.11+ on the server
        local python_cmd=$(remote_exec "command -v python3.11 || command -v python3.12 || command -v python3.13 || command -v python3 || command -v python" 2>/dev/null | head -1)
        
        if [ -z "$python_cmd" ]; then
            print_error "Python 3 not found on the server."
            print_info "Please install Python 3.11+ on the server."
            exit 1
        fi
        
        # Check if python3-venv is available
        local python_version=$(remote_exec "$python_cmd --version 2>&1 | grep -oP '\d+\.\d+' | head -1")
        local venv_package="python${python_version}-venv"
        
        print_info "Using Python: $python_cmd (version: $python_version)"
        
        # Check if venv module is available
        if ! remote_exec "$python_cmd -m venv --help" >/dev/null 2>&1; then
            print_warning "python3-venv package not installed. Attempting to install..."
            
            # Try to install with sudo (non-interactive)
            if remote_exec "sudo -n apt-get update && sudo -n apt-get install -y ${venv_package}" >/dev/null 2>&1; then
                print_success "python3-venv package installed"
            else
                print_error "Cannot install python3-venv without sudo password."
                print_info "Please run this command manually on the server:"
                echo "  sudo apt-get update && sudo apt-get install -y ${venv_package}"
                print_info "Then run ./deploy.sh again to continue."
                exit 1
            fi
        fi
        
        # Create virtual environment
        print_info "Creating virtual environment..."
        local venv_output=$(remote_exec "cd ${DEPLOY_DIR}/app && $python_cmd -m venv venv 2>&1")
        local venv_exit=$?
        
        if [ $venv_exit -eq 0 ]; then
            print_success "Virtual environment created"
        else
            print_error "Failed to create virtual environment."
            echo "Error: $venv_output"
            print_info "Please ensure python3-venv is installed: sudo apt-get install -y ${venv_package}"
            exit 1
        fi
        
        # Upgrade pip and install dependencies
        print_info "Upgrading pip and installing dependencies..."
        remote_exec "cd ${DEPLOY_DIR}/app && venv/bin/pip install --upgrade pip && venv/bin/pip install -q -r requirements.txt"
        print_success "Dependencies installed"
    else
        print_success "Virtual environment exists"
    fi
    
    # 5.5. Update Python dependencies (always, to ensure latest)
    print_info "Updating Python dependencies..."
    remote_exec "cd ${DEPLOY_DIR}/app && venv/bin/pip install -q --upgrade -r requirements.txt"
    print_success "Python dependencies updated"
    
    # 5. Run database migrations
    print_info "Running database migrations..."
    remote_exec "cd ${DEPLOY_DIR} && app/venv/bin/python -m alembic upgrade head"
    if [ $? -eq 0 ]; then
        print_success "Database migrations completed"
    else
        print_error "Database migration failed!"
        exit 1
    fi
    
    # 7. Build frontend
    print_info "Building frontend (this may take a few minutes)..."
    remote_exec "cd ${DEPLOY_DIR}/ui && NEXT_PUBLIC_BASE_PATH='${DEPLOY_PATH}' npm ci --production && NEXT_PUBLIC_BASE_PATH='${DEPLOY_PATH}' npm run build"
    if [ $? -eq 0 ]; then
        print_success "Frontend build completed"
    else
        print_error "Frontend build failed!"
        exit 1
    fi
    
    # 8. Update Nginx configuration
    print_info "Updating Nginx configuration..."
    if [ -f "deploy/nginx-luboss.conf" ]; then
        remote_copy "deploy/nginx-luboss.conf" "/tmp/nginx-luboss.conf"
        remote_exec_sudo "cp /tmp/nginx-luboss.conf ${NGINX_SITES_AVAILABLE}/${NGINX_SITE_NAME}"
        remote_exec_sudo "ln -sf ${NGINX_SITES_AVAILABLE}/${NGINX_SITE_NAME} ${NGINX_SITES_ENABLED}/${NGINX_SITE_NAME}"
        
        # Test Nginx configuration
        print_info "Testing Nginx configuration..."
        if remote_exec_sudo "nginx -t" 2>&1 | grep -q "successful"; then
            print_success "Nginx configuration is valid"
            remote_exec_sudo "systemctl reload nginx"
            print_success "Nginx reloaded"
        else
            print_error "Nginx configuration test failed!"
            remote_exec_sudo "nginx -t"
            exit 1
        fi
    else
        print_warning "Nginx configuration file not found, skipping Nginx update"
    fi
    
    # 9. Restart backend service
    print_info "Restarting backend service..."
    if remote_exec "systemctl is-active --quiet ${BACKEND_SERVICE_NAME} 2>/dev/null || sudo -n systemctl is-active --quiet ${BACKEND_SERVICE_NAME}" 2>/dev/null; then
        remote_exec_sudo "systemctl restart ${BACKEND_SERVICE_NAME}"
        print_success "Backend service restarted"
    else
        print_warning "Backend service not running, starting it..."
        remote_exec_sudo "systemctl start ${BACKEND_SERVICE_NAME}" || print_warning "Failed to start backend service (may need manual setup)"
    fi
    
    # 10. Restart frontend service
    print_info "Restarting frontend service..."
    if remote_exec "systemctl is-active --quiet ${FRONTEND_SERVICE_NAME} 2>/dev/null || sudo -n systemctl is-active --quiet ${FRONTEND_SERVICE_NAME}" 2>/dev/null; then
        remote_exec_sudo "systemctl restart ${FRONTEND_SERVICE_NAME}"
        print_success "Frontend service restarted"
    else
        print_warning "Frontend service not running, starting it..."
        remote_exec_sudo "systemctl start ${FRONTEND_SERVICE_NAME}" || print_warning "Failed to start frontend service (may need manual setup)"
    fi
    
    # 11. Verify deployment
    print_info "Verifying deployment..."
    sleep 2
    
    # Check backend health
    if remote_exec "curl -sf http://localhost:${BACKEND_PORT}/health > /dev/null" 2>/dev/null; then
        print_success "Backend health check passed"
    else
        print_warning "Backend health check failed (service may still be starting)"
    fi
    
    # Check frontend
    if remote_exec "curl -sf http://localhost:${FRONTEND_PORT} > /dev/null" 2>/dev/null; then
        print_success "Frontend is responding"
    else
        print_warning "Frontend check failed (service may still be starting)"
    fi
    
    print_success "Deployment completed!"
    print_info "Application should be available at: https://${DOMAIN}${DEPLOY_PATH}"
    print_info "Backend API: https://${DOMAIN}${DEPLOY_PATH}/api"
    
    # Create deployment log
    print_info "Creating deployment log..."
    create_deployment_log
    print_success "Deployment log created"
}

# Main execution
if [ "$DRY_RUN" = true ]; then
    dry_run_deploy
else
    deploy
fi
