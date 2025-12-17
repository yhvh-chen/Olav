#!/usr/bin/env bash
#
# OLAV minimal setup (env-driven)
# Matches logic of setup.ps1
#
# Usage:
#   ./setup.sh                 # Auto (defaults to QuickTest unless .env sets OLAV_MODE=production)
#   ./setup.sh --mode QuickTest
#   ./setup.sh --mode Production
#

set -euo pipefail

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

info() { echo -e "${CYAN}[INFO] $*${NC}"; }
success() { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}" >&2; exit 1; }

generate_secret() {
    # Generate 32 bytes hex string (64 chars)
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32
    else
        python3 -c "import secrets; print(secrets.token_hex(32))"
    fi
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
    else
        docker compose "$@"
    fi
}

# Update a key in .env or append if missing
set_env_value() {
    local key="$1"
    local val="$2"
    local file="$3"

    if grep -q "^[[:space:]]*${key}[[:space:]]*=" "$file"; then
        # Use temp file for sed to avoid issues on some platforms
        local tmp=$(mktemp)
        sed "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${val}|" "$file" > "$tmp"
        mv "$tmp" "$file"
    else
        echo "${key}=${val}" >> "$file"
    fi
}

wait_for_url() {
    local url="$1"
    local timeout="${2:-120}"
    local start_time=$(date +%s)

    info "Waiting for $url (timeout: ${timeout}s)..."
    while true; do
        if curl -s -f -o /dev/null "$url"; then
            success "Endpoint reachable: $url"
            return 0
        fi
        local current_time=$(date +%s)
        if (( current_time - start_time > timeout )); then
            fail "Timed out waiting for $url"
        fi
        sleep 2
    done
}

wait_for_container_healthy() {
    local container="$1"
    local timeout="${2:-240}"
    local start_time=$(date +%s)

    info "Waiting for container healthy: $container (timeout: ${timeout}s)..."
    while true; do
        local status
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "")
        if [[ "$status" == "healthy" ]]; then
            success "$container is healthy"
            return 0
        fi
        local current_time=$(date +%s)
        if (( current_time - start_time > timeout )); then
            fail "Timed out waiting for $container to be healthy (status: $status)"
        fi
        sleep 3
    done
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

# Parse args
MODE_ARG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE_ARG="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

require_cmd docker
require_cmd uv

if [[ ! -f "$ENV_FILE" ]]; then
    fail ".env not found. Please create it first:\n  cp .env.example .env\n  ${EDITOR:-vi} .env"
fi

# Load .env vars (ignoring comments)
set -a
source <(grep -v '^#' "$ENV_FILE" | sed 's/^export //')
set +a

# Resolve Mode
if [[ -n "$MODE_ARG" ]]; then
    RESOLVED_MODE="$MODE_ARG"
else
    case "${OLAV_MODE:-quicktest}" in
        production|prod|Production) RESOLVED_MODE="Production" ;;
        *) RESOLVED_MODE="QuickTest" ;;
    esac
fi

info "OLAV setup (mode: $RESOLVED_MODE)"

# Apply runtime defaults
if [[ "$RESOLVED_MODE" == "Production" ]]; then
    export AUTH_DISABLED=false
    export OPENSEARCH_SECURITY_DISABLED=false
    export OLAV_MODE="production"
else
    export AUTH_DISABLED=true
    export OPENSEARCH_SECURITY_DISABLED=true
    export OLAV_MODE="quicktest"
    unset OLAV_API_TOKEN || true
fi

# Check NETBOX_SECRET_KEY
NETBOX_SECRET_KEY="${NETBOX_SECRET_KEY:-}"
if [[ -z "$NETBOX_SECRET_KEY" || ${#NETBOX_SECRET_KEY} -lt 50 ]]; then
    if [[ "$RESOLVED_MODE" == "Production" ]]; then
        fail "NETBOX_SECRET_KEY must be at least 50 characters for Production mode."
    fi
    
    NEW_SECRET=$(generate_secret)
    set_env_value "NETBOX_SECRET_KEY" "$NEW_SECRET" "$ENV_FILE"
    export NETBOX_SECRET_KEY="$NEW_SECRET"
    warn "Generated temporary NETBOX_SECRET_KEY (saved to .env)"
    GENERATED_NETBOX_SECRET=true
else
    GENERATED_NETBOX_SECRET=false
fi

# Check required vars
REQUIRED_VARS=(OLAV_SERVER_PORT OLAV_APP_PORT NETBOX_PORT POSTGRES_PORT OPENSEARCH_PORT)
if [[ "$RESOLVED_MODE" == "Production" ]]; then
    REQUIRED_VARS+=(OLAV_API_TOKEN)
fi

MISSING=()
for v in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!v:-}" ]]; then MISSING+=("$v"); fi
done
if (( ${#MISSING[@]} > 0 )); then
    fail "Missing required .env keys: ${MISSING[*]}"
fi

# Configs
NETBOX_ENABLED="${NETBOX_ENABLED:-true}"
NETBOX_AUTO_INIT="${NETBOX_AUTO_INIT:-true}"
NETBOX_AUTO_INIT_FORCE="${NETBOX_AUTO_INIT_FORCE:-false}"
INVENTORY_CSV="${INVENTORY_CSV_PATH:-config/inventory.csv}"
NETBOX_PORT="${NETBOX_PORT_EXTERNAL:-${NETBOX_PORT:-8080}}"
SERVER_PORT="${OLAV_SERVER_PORT_EXTERNAL:-${OLAV_SERVER_PORT:-8000}}"

# Prepare Images
info "Preparing Docker images..."
PROFILE_ARGS=()
if [[ "$NETBOX_ENABLED" == "true" ]]; then
    PROFILE_ARGS+=(--profile netbox)
fi

# Pull in background
(cd "$ROOT_DIR" && compose "${PROFILE_ARGS[@]}" pull -q) &
PULL_PID=$!

# Build in foreground
(cd "$ROOT_DIR" && compose "${PROFILE_ARGS[@]}" build)

wait $PULL_PID || warn "Docker pull failed (continuing)"

# Start Services
if [[ "$NETBOX_ENABLED" == "true" ]]; then
    info "NetBox enabled: starting NetBox first..."
    (cd "$ROOT_DIR" && compose --profile netbox up -d netbox-postgres netbox-redis netbox-redis-cache netbox)
    
    wait_for_container_healthy "olav-netbox" 300

    if [[ "$NETBOX_AUTO_INIT" == "true" ]]; then
        info "Initializing NetBox inventory..."
        ARGS=(run olav init netbox --csv "$INVENTORY_CSV")
        if [[ "$NETBOX_AUTO_INIT_FORCE" == "true" ]]; then ARGS+=(--force); fi
        
        (cd "$ROOT_DIR" && uv "${ARGS[@]}") || warn "NetBox init failed (check logs)"
    fi

    info "Starting remaining services..."
    (cd "$ROOT_DIR" && compose --profile netbox up -d)
else
    info "NetBox disabled: starting services..."
    (cd "$ROOT_DIR" && compose up -d)
fi

success "Docker services started"

# Wait for Postgres and OpenSearch before schema init
info "Waiting for Postgres and OpenSearch to be ready..."
PG_OK=false
OS_OK=false

if wait_for_container_healthy "olav-postgres" 60; then
    PG_OK=true
fi

if wait_for_container_healthy "olav-opensearch" 120; then
    OS_OK=true
fi

# Initialize OpenSearch indexes and PostgreSQL Checkpointer tables
if [[ "$PG_OK" == "true" && "$OS_OK" == "true" ]]; then
    info "Initializing OpenSearch indexes and PostgreSQL tables..."
    INIT_ARGS=(run olav init all)
    if [[ "$NETBOX_AUTO_INIT_FORCE" == "true" ]]; then INIT_ARGS+=(--force); fi
    
    (cd "$ROOT_DIR" && uv "${INIT_ARGS[@]}") || warn "Schema initialization had warnings"
    success "Schema and index initialization completed"
else
    warn "Postgres or OpenSearch not healthy, skipping schema init"
fi

if [[ "$GENERATED_NETBOX_SECRET" == "true" ]]; then
    info "Recreating NetBox to apply generated secret..."
    (cd "$ROOT_DIR" && compose --profile netbox up -d --force-recreate netbox)
fi

wait_for_url "http://127.0.0.1:${SERVER_PORT}/health" 180

# Status Check
info "Running status check..."
STATUS_ARGS=(run olav status --server "http://127.0.0.1:${SERVER_PORT}")
if [[ "$RESOLVED_MODE" == "Production" ]]; then
    export OLAV_API_TOKEN="${OLAV_API_TOKEN}"
else
    unset OLAV_API_TOKEN || true
fi

(cd "$ROOT_DIR" && uv "${STATUS_ARGS[@]}") || warn "Status check failed"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}              Setup Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [[ "$RESOLVED_MODE" == "QuickTest" ]]; then
    echo -e "${YELLOW}Quick start (QuickTest):${NC}"
    echo -e "${GRAY}  uv run olav${NC}"
    echo -e "${GRAY}  # (auth is disabled in QuickTest)${NC}"
else
    echo -e "${YELLOW}Next steps (Production):${NC}"
    echo -e "${GRAY}  # Register a client${NC}"
    echo -e "${GRAY}  export OLAV_API_TOKEN='<master-token-from-.env>'${NC}"
    echo -e "${GRAY}  uv run olav register --name 'my-laptop' --server http://127.0.0.1:${SERVER_PORT}${NC}"
    echo -e "${GRAY}  uv run olav${NC}"
fi
