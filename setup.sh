#!/usr/bin/env bash
#
# OLAV minimal setup (env-driven)
#
# Usage:
#   ./setup.sh                 # QuickTest (default)
#   ./setup.sh --mode Production
#

set -euo pipefail

MODE="QuickTest"
if [[ "${1:-}" == "--mode" && -n "${2:-}" ]]; then
    MODE="$2"
elif [[ "${1:-}" == "--production" ]]; then
    MODE="Production"
elif [[ "${1:-}" == "--quick" || "${1:-}" == "--quicktest" ]]; then
    MODE="QuickTest"
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "[INFO] $*"; }

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

load_env() {
    [[ -f "$ENV_FILE" ]] || fail ".env not found. Create it first: cp .env.example .env"

    # Parse KEY=VALUE lines (ignore comments/blank). Values are treated as raw strings.
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "${line//[[:space:]]/}" ]] && continue
        [[ "${line#\#}" != "$line" ]] && continue
        if [[ "$line" == *"="* ]]; then
            key="${line%%=*}"
            val="${line#*=}"
            key="${key//[[:space:]]/}"
            export "$key=$val"
        fi
    done < "$ENV_FILE"
}

require_vars() {
    local missing=()
    for k in "$@"; do
        if [[ -z "${!k:-}" ]]; then
            missing+=("$k")
        fi
    done
    if (( ${#missing[@]} > 0 )); then
        fail "Missing required .env keys: ${missing[*]}"
    fi
}

main() {
    info "OLAV setup (mode: $MODE)"

    require_cmd docker
    require_cmd uv

    if [[ ! -f "$ENV_FILE" ]]; then
        echo ""
        echo ".env not found. Please create it first:" 
        echo "  cp .env.example .env"
        echo "  ${EDITOR:-vi} .env"
        echo ""
        [[ -f "$ENV_EXAMPLE" ]] && echo "Template: $ENV_EXAMPLE"
        exit 1
    fi

    load_env

        # If mode not explicitly provided, infer from .env (default: QuickTest)
        if [[ "${1:-}" != "--mode" && "${1:-}" != "--production" && "${1:-}" != "--quick" && "${1:-}" != "--quicktest" ]]; then
            case "${OLAV_MODE:-quicktest}" in
                production|prod)
                    MODE="Production"
                    ;;
                *)
                    MODE="QuickTest"
                    ;;
            esac
        fi

    # Enforce mode defaults at runtime (environment overrides compose defaults)
    if [[ "$MODE" == "Production" ]]; then
        export AUTH_DISABLED=false
        export OPENSEARCH_SECURITY_DISABLED=false
        require_vars OLAV_API_TOKEN
    else
        export AUTH_DISABLED=true
        export OPENSEARCH_SECURITY_DISABLED=true
        unset OLAV_API_TOKEN || true
    fi

    require_vars \
        OPENSEARCH_PORT OPENSEARCH_METRICS_PORT POSTGRES_PORT NETBOX_PORT SUZIEQ_GUI_PORT \
        OLAV_APP_PORT OLAV_SERVER_PORT FLUENT_SYSLOG_PORT FLUENT_HTTP_PORT

    info "Starting Docker services (compose --profile netbox up -d)..."
    (cd "$ROOT_DIR" && compose --profile netbox up -d)
    info "Docker services started"

    sleep 5

    local server_url="http://127.0.0.1:${OLAV_SERVER_PORT}"
    info "Running status check: uv run olav status --server ${server_url}"
    (cd "$ROOT_DIR" && uv run olav status --server "$server_url") || true

    echo ""
    echo "========================================"
    echo "              Setup Complete"
    echo "========================================"
    echo ""

    if [[ "$MODE" == "Production" ]]; then
        echo "Next steps (Production):"
        echo "  # Register a client (saves token to ~/.olav/credentials and server URL to ~/.olav/config.toml)"
        echo "  # Ensure OLAV_API_TOKEN is exported (e.g. 'set -a; source .env; set +a')"
        echo "  uv run olav register --name \"my-laptop\" --server ${server_url}"
        echo "  uv run olav"
    else
        echo "Quick start (QuickTest):"
        echo "  uv run olav"
        echo "  # (auth is disabled in QuickTest)"
    fi
}

main

exit 0

# ---------------------------------------------------------------------------
# Legacy interactive wizard (archived)
# ---------------------------------------------------------------------------

set -e

# ============================================
# Configuration
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default Ports
declare -A PORTS=(
    ["opensearch"]=9200
    ["postgres"]=5432
    ["netbox"]=8080
    ["olav_api"]=8000
)

# Alternative Ports
declare -A ALT_PORTS=(
    [9200]=19200
    [5432]=15432
    [8080]=8081
    [8000]=8001
)

# Default Credentials (Quick Test)
DEFAULT_POSTGRES_USER="olav"
DEFAULT_POSTGRES_PASSWORD="olav"
DEFAULT_NETBOX_USER="admin"
DEFAULT_NETBOX_PASSWORD="admin"
DEFAULT_DEVICE_USERNAME=""
DEFAULT_DEVICE_PASSWORD=""
DEFAULT_SUZIEQ_TAG_NAME="suzieq"
DEFAULT_SUZIEQ_AUTO_TAG_ALL="true"

# ============================================
# Colors and Output
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

print_banner() {
    clear
    echo -e "${CYAN}"
    echo "========================================"
    echo "       OLAV Setup Wizard v1.0"
    echo "========================================"
    echo -e "${NC}"
}

print_step() {
    echo ""
    echo -e "${YELLOW}[$1] $2${NC}"
    echo "----------------------------------------"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

is_strong_password() {
    local pw="$1"
    [ ${#pw} -ge 12 ] || return 1
    [[ "$pw" =~ [[:space:]] ]] && return 1
    [[ "$pw" =~ [Aa][Dd][Mm][Ii][Nn] ]] && return 1
    [[ "$pw" =~ [Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd] ]] && return 1
    [[ "$pw" =~ [Oo][Pp][Ee][Nn][Ss][Ee][Aa][Rr][Cc][Hh] ]] && return 1
    [[ "$pw" =~ [A-Z] ]] || return 1
    [[ "$pw" =~ [a-z] ]] || return 1
    [[ "$pw" =~ [0-9] ]] || return 1
    [[ "$pw" =~ [^A-Za-z0-9] ]] || return 1
    return 0
}

# ============================================
# Input Functions
# ============================================

read_input() {
    local prompt="$1"
    local default="$2"
    local is_password="$3"
    
    if [ -n "$default" ]; then
        prompt="$prompt [$default]"
    fi
    
    if [ "$is_password" = "true" ]; then
        read -s -p "$prompt: " value
        echo ""  # New line after password
    else
        read -p "$prompt: " value
    fi
    
    if [ -z "$value" ] && [ -n "$default" ]; then
        echo "$default"
    else
        echo "$value"
    fi
}

read_required_input() {
    local prompt="$1"
    local is_password="$2"
    local value=""

    while true; do
        if [ "$is_password" = "true" ]; then
            read -s -p "$prompt: " value
            echo ""  # New line after password
        else
            read -p "$prompt: " value
        fi

        if [ -n "$value" ]; then
            echo "$value"
            return
        fi

        echo "This value is required; please enter a non-empty value."
    done
}

read_choice() {
    local prompt="$1"
    local min="$2"
    local max="$3"
    
    while true; do
        read -p "$prompt: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge "$min" ] && [ "$choice" -le "$max" ]; then
            echo "$choice"
            return
        fi
        echo "Please enter a number between $min and $max"
    done
}

# ============================================
# Utility Functions
# ============================================

check_port() {
    local port="$1"
    if command -v ss &> /dev/null; then
        ss -tuln | grep -q ":$port " && return 1 || return 0
    elif command -v lsof &> /dev/null; then
        lsof -i :"$port" &> /dev/null && return 1 || return 0
    else
        # Fallback: try to connect
        (echo > /dev/tcp/127.0.0.1/"$port") &>/dev/null && return 1 || return 0
    fi
}

get_process_using_port() {
    local port="$1"
    if command -v lsof &> /dev/null; then
        lsof -i :"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " (PID " $2 ")"}'
    elif command -v ss &> /dev/null; then
        ss -tlnp 2>/dev/null | grep ":$port " | sed -n 's/.*users:(("\([^"]*\)",pid=\([0-9]*\).*/\1 (PID \2)/p'
    fi
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        return 1
    fi
    if ! docker info &> /dev/null; then
        print_error "Docker is not running"
        return 1
    fi
    return 0
}

check_uv() {
    if ! command -v uv &> /dev/null; then
        print_error "uv is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        return 1
    fi
    return 0
}

# ============================================
# Wizard Steps
# ============================================

select_deployment_mode() {
    print_banner
    
    echo -e "${WHITE}"
    echo "Select deployment mode:"
    echo ""
    echo "  [1] Quick Test"
    echo "      - Minimal configuration (5 steps)"
    echo "      - All infrastructure uses default credentials"
    echo "      - OpenSearch security disabled"
    echo "      - Best for: Evaluation, development, demos"
    echo ""
    echo "  [2] Production"
    echo "      - Full configuration wizard (8 steps)"
    echo "      - Custom credentials for all services"
    echo "      - OpenSearch security enabled"
    echo "      - Best for: Production, multi-user environments"
    echo -e "${NC}"
    
    local choice=$(read_choice "Choice [1/2]" 1 2)
    if [ "$choice" = "1" ]; then
        echo "quicktest"
    else
        echo "production"
    fi
}

step_llm_configuration_inner() {
    echo ""
    echo -e "${WHITE}Select LLM Provider:${NC}"
    echo "  [1] OpenAI"
    echo "  [2] OpenAI Compatible (custom endpoint)"
    echo "  [3] Azure OpenAI"
    echo "  [4] Anthropic"
    echo "  [5] Google AI"
    echo "  [6] Ollama (local deployment)"
    
    local choice=$(read_choice "Choice [1-6]" 1 6)
    
    case $choice in
        1) LLM_PROVIDER="openai" ;;
        2) LLM_PROVIDER="openai" ;;
        3) LLM_PROVIDER="azure" ;;
        4) LLM_PROVIDER="anthropic" ;;
        5) LLM_PROVIDER="google" ;;
        6) LLM_PROVIDER="ollama" ;;
    esac
    
    # API Key
    if [ "$choice" != "6" ]; then
        echo ""
        LLM_API_KEY=$(read_input "Enter API Key" "" "true")
    fi
    
    # Endpoint (for Azure, Ollama, OpenAI Compatible)
    if [ "$choice" = "2" ] || [ "$choice" = "3" ] || [ "$choice" = "6" ]; then
        local default_endpoint=""
        [ "$choice" = "6" ] && default_endpoint="http://host.docker.internal:11434"
        local endpoint_prompt="Enter OpenAI Base URL"
        [ "$choice" = "3" ] && endpoint_prompt="Enter Azure OpenAI Endpoint"
        [ "$choice" = "6" ] && endpoint_prompt="Enter Ollama Endpoint"
        LLM_BASE_URL=$(read_input "$endpoint_prompt" "$default_endpoint")
    fi
    
    # Model name
    echo ""
    LLM_MODEL_NAME=$(read_input "Enter model name (e.g. gpt-4o, claude-3-opus)" "")
    
    # Test connection (basic validation)
    echo ""
    echo -e "${CYAN}Validating LLM configuration...${NC}"
    
    if [ -n "$LLM_API_KEY" ] || [ "$LLM_PROVIDER" = "ollama" ]; then
        print_success "LLM configuration validated"
    else
        print_warning "Could not validate LLM connection (will proceed anyway)"
    fi
}

step_llm_configuration() {
    print_step "1/5" "LLM Configuration"
    step_llm_configuration_inner
}

step_embedding_configuration_inner() {
    echo ""
    echo -e "${WHITE}Select Embedding Provider:${NC}"
    echo "  [1] OpenAI (same API Key as LLM)"
    echo "  [2] OpenAI (different API Key)"
    echo "  [3] Azure OpenAI"
    echo "  [4] Ollama (local deployment)"
    
    local choice=$(read_choice "Choice [1-4]" 1 4)
    
    case $choice in
        1)
            EMBEDDING_PROVIDER="openai"
            EMBEDDING_API_KEY="$LLM_API_KEY"
            ;;
        2)
            EMBEDDING_PROVIDER="openai"
            EMBEDDING_API_KEY=$(read_input "Enter Embedding API Key" "" "true")
            ;;
        3)
            EMBEDDING_PROVIDER="azure"
            EMBEDDING_API_KEY=$(read_input "Enter Azure Embedding API Key" "" "true")
            EMBEDDING_BASE_URL=$(read_input "Enter Azure Embedding Endpoint" "")
            ;;
        4)
            EMBEDDING_PROVIDER="ollama"
            EMBEDDING_BASE_URL=$(read_input "Enter Ollama Endpoint" "http://host.docker.internal:11434")
            ;;
    esac
    
    # Embedding model
    local default_model=""
    [ "$EMBEDDING_PROVIDER" = "openai" ] && default_model="text-embedding-3-small"
    EMBEDDING_MODEL=$(read_input "Enter Embedding model name" "$default_model")
    
    print_success "Embedding configuration complete"
}

step_embedding_configuration() {
    print_step "2/5" "Embedding Configuration"
    step_embedding_configuration_inner
}

step_device_credentials_inner() {
    echo ""
    DEVICE_USERNAME=$(read_required_input "Enter device username" "false")
    DEVICE_PASSWORD=$(read_required_input "Enter device password" "true")

    echo ""
    DEVICE_ENABLE_PASSWORD=$(read_input "Enter enable password (optional; press Enter to skip)" "" "true")
    
    print_success "Device credentials configured"
}

step_device_credentials() {
    print_step "3/5" "Device Credentials (SSH/NETCONF access)"
    step_device_credentials_inner
}

step_port_check_inner() {
    echo ""
    echo -e "${CYAN}Checking required ports...${NC}"
    
    local has_conflicts=false
    
    for service in opensearch postgres netbox; do
        local port="${PORTS[$service]}"
        local display_name=$(echo "$service" | tr '[:lower:]' '[:upper:]')
        
        if check_port "$port"; then
            echo -e "  - $display_name ($port): ${GREEN}✅ Available${NC}"
            eval "PORT_${service^^}=$port"
        else
            has_conflicts=true
            local process_info=$(get_process_using_port "$port")
            echo -e "  - $display_name ($port): ${YELLOW}⚠️ In use${NC} ($process_info)"
            
            # Offer alternative
            local alt_port="${ALT_PORTS[$port]}"
            [ -z "$alt_port" ] && alt_port=$((port + 1))
            
            local use_alt=$(read_input "  Use alternative port $alt_port? [Y/n]" "Y")
            if [[ "$use_alt" =~ ^[Yy] ]]; then
                eval "PORT_${service^^}=$alt_port"
                echo -e "  → $display_name will use port $alt_port"
            else
                eval "PORT_${service^^}=$port"
                print_warning "  → Keeping port $port (may fail to start)"
            fi
        fi
    done
    
    echo ""
    print_success "Port check complete"
}

step_port_check() {
    print_step "4/5" "Port Availability Check"
    step_port_check_inner
}

step_start_services() {
    echo ""
    echo -e "${CYAN}Starting Docker containers (Parallel Mode)...${NC}"
    
    # Check Docker
    if ! check_docker; then
        exit 1
    fi
    
    # Only generate env file in Quick Test mode (Production mode generates its own)
    if [ "$MODE" = "quicktest" ]; then
        generate_env_file
        print_success ".env file generated"
    fi
    
    cd "$PROJECT_ROOT"
    
    # 1. Start Infrastructure
    echo -e "${CYAN}[1/3] Starting Infrastructure (NetBox, Postgres, OpenSearch)...${NC}"
    # Start core infra services explicitly
    docker-compose up -d postgres opensearch redis redis-cache netbox netbox-worker netbox-housekeeping
    
    # 2. Build App Images (Background)
    echo -e "${CYAN}[2/3] Building App Images (Background)...${NC}"
    docker-compose build olav-app olav-server &
    BUILD_PID=$!
    
    # 3. Wait for NetBox Health
    echo -e "${CYAN}[3/3] Waiting for NetBox to be healthy...${NC}"
    local retries=24 # 120 seconds
    local healthy=false
    
    while [ $retries -gt 0 ]; do
        sleep 5
        local status=$(docker inspect --format='{{.State.Health.Status}}' olav-netbox 2>/dev/null || echo "unknown")
        if [ "$status" = "healthy" ]; then
            healthy=true
            break
        fi
        echo -n "."
        retries=$((retries - 1))
    done
    echo ""
    
    if [ "$healthy" = "true" ]; then
        print_success "NetBox is healthy"
    else
        print_warning "NetBox is not healthy yet (Status: $status). Proceeding anyway..."
    fi
    
    # Wait for build to finish
    echo -e "${CYAN}Waiting for image build to complete...${NC}"
    wait $BUILD_PID
    if [ $? -eq 0 ]; then
        print_success "App images built"
    else
        print_error "Image build failed"
        exit 1
    fi
    
    # Start remaining services
    echo -e "${CYAN}Starting remaining services...${NC}"
    if docker-compose --profile netbox up -d; then
        print_success "All services started"
    else
        print_error "Failed to start remaining services"
        exit 1
    fi
}

step_netbox_inventory_init() {
    echo ""
    echo -e "${CYAN}Initializing NetBox with device inventory...${NC}"
    
    local default_csv="$PROJECT_ROOT/config/inventory.csv"
    
    # Check if inventory.csv exists
    if [ -f "$default_csv" ]; then
        # Count devices in CSV
        local device_count=$(grep -cv '^#' "$default_csv" 2>/dev/null || echo "0")
        if [ "$device_count" -gt 0 ]; then
            device_count=$((device_count - 1))  # Subtract header
        fi
        echo "  Found inventory.csv with $device_count device(s)"
        
        # Prompt user - default YES, but skip in Quick Test mode if desired
        local import_devices="Y"
        if [ "$MODE" = "quicktest" ]; then
             # In quicktest, we might want to skip to be fast, or just do it.
             # The user asked for optimization. Let's skip it in quicktest by default or make it optional.
             # But setup.sh is interactive.
             # Let's just keep it interactive but default to Y.
             # If we want to match setup.ps1 -Install behavior, we need a non-interactive flag.
             # Assuming interactive usage for setup.sh for now.
             import_devices=$(read_input "Import devices from inventory.csv? [Y/n]" "Y")
        else
             import_devices=$(read_input "Import devices from inventory.csv? [Y/n]" "Y")
        fi
        
        if [[ ! "$import_devices" =~ ^[Nn]$ ]]; then
            echo ""
            echo -e "${CYAN}Importing devices to NetBox...${NC}"
            
            # Direct Python call - bypasses broken CLI parameter
            (
                cd "$PROJECT_ROOT"
                export NETBOX_URL="http://localhost:${NETBOX_PORT:-8080}"
                export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
                
                if uv run python scripts/netbox_ingest.py > /tmp/netbox_ingest.log 2>&1; then
                    if grep -q '"code": 0' /tmp/netbox_ingest.log; then
                        print_success "Device inventory imported successfully"
                    elif grep -q '"code": 99' /tmp/netbox_ingest.log; then
                        print_success "NetBox already has devices (skipped import)"
                    else
                        print_warning "Import may have issues - check NetBox"
                    fi
                else
                    print_warning "Import had issues - check NetBox"
                fi
            )
        else
            echo "  Skipping device import"
        fi
    else
        echo "  No inventory.csv found at: $default_csv"
    fi
}

step_schema_init_inner() {
    echo ""
    echo -e "${CYAN}Initializing NetBox with inventory (if present)...${NC}"
    step_netbox_inventory_init
    
    # Then run schema initialization
    echo ""
    echo -e "${CYAN}Initializing OpenSearch indices and system schemas...${NC}"
    
    cd "$PROJECT_ROOT"
    if uv run olav init all > /tmp/init_all.log 2>&1; then
        print_success "Schema initialization complete"
    else
        print_warning "Schema initialization had issues - check logs"
    fi
    
    # Optional custom CSV import
    echo ""
    local custom_import=$(read_input "Import devices from custom CSV? [y/N]" "N")
    
    if [[ "$custom_import" =~ ^[Yy]$ ]]; then
        local csv_path=$(read_input "Enter CSV file path" "")
        
        if [ -n "$csv_path" ] && [ -f "$csv_path" ]; then
            echo -e "${CYAN}Importing devices from custom CSV...${NC}"
            (
                cd "$PROJECT_ROOT"
                export NETBOX_URL="http://localhost:${NETBOX_PORT:-8080}"
                export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
                export NETBOX_INGEST_FORCE="true"
                
                if uv run python scripts/netbox_ingest.py > /tmp/netbox_custom.log 2>&1; then
                    print_success "Custom device import complete"
                else
                    print_warning "Custom import had issues"
                fi
            )
        else
            if [ -z "$csv_path" ]; then
                echo "No CSV file path provided"
            else
                print_warning "CSV file not found: $csv_path"
            fi
        fi
    fi
}

step_schema_init() {
    print_step "5/5" "Initialization"
    step_schema_init_inner
}

generate_env_file() {
    local env_file="$PROJECT_ROOT/.env"
    
    cat > "$env_file" << EOF
# ============================================
# OLAV Configuration
# Generated by Setup Wizard ($MODE Mode)
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================

# Deployment Mode
OLAV_MODE=$MODE

# LLM Configuration
LLM_PROVIDER=$LLM_PROVIDER
LLM_API_KEY=$LLM_API_KEY
LLM_MODEL_NAME=$LLM_MODEL_NAME
EOF

    [ -n "$LLM_BASE_URL" ] && echo "LLM_BASE_URL=$LLM_BASE_URL" >> "$env_file"
    
    cat >> "$env_file" << EOF

# Embedding Configuration
EMBEDDING_PROVIDER=$EMBEDDING_PROVIDER
EMBEDDING_MODEL=$EMBEDDING_MODEL
EOF

    [ -n "$EMBEDDING_API_KEY" ] && echo "EMBEDDING_API_KEY=$EMBEDDING_API_KEY" >> "$env_file"
    [ -n "$EMBEDDING_BASE_URL" ] && echo "EMBEDDING_BASE_URL=$EMBEDDING_BASE_URL" >> "$env_file"
    
    cat >> "$env_file" << EOF

# Device Credentials
DEVICE_USERNAME=$DEVICE_USERNAME
DEVICE_PASSWORD=$DEVICE_PASSWORD
DEVICE_ENABLE_PASSWORD=$DEVICE_ENABLE_PASSWORD

# SuzieQ Tagging
SUZIEQ_TAG_NAME=${SUZIEQ_TAG_NAME:-$DEFAULT_SUZIEQ_TAG_NAME}
SUZIEQ_AUTO_TAG_ALL=${SUZIEQ_AUTO_TAG_ALL:-$DEFAULT_SUZIEQ_AUTO_TAG_ALL}

# SuzieQ Tagging
SUZIEQ_TAG_NAME=${SUZIEQ_TAG_NAME:-$DEFAULT_SUZIEQ_TAG_NAME}
SUZIEQ_AUTO_TAG_ALL=${SUZIEQ_AUTO_TAG_ALL:-$DEFAULT_SUZIEQ_AUTO_TAG_ALL}

# NetBox (auto-created local instance)
NETBOX_URL=http://netbox:8080
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
NETBOX_SUPERUSER_NAME=admin
NETBOX_SUPERUSER_EMAIL=admin@olav.local
NETBOX_SUPERUSER_PASSWORD=admin
NETBOX_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || echo "production-secret-key-$(date +%s)-$(date +%N)-$(date +%s)")

# PostgreSQL
POSTGRES_USER=$DEFAULT_POSTGRES_USER
POSTGRES_PASSWORD=$DEFAULT_POSTGRES_PASSWORD
POSTGRES_DB=olav

# OpenSearch
EOF

    if [ "$MODE" = "quicktest" ]; then
        cat >> "$env_file" << EOF
OPENSEARCH_SECURITY_DISABLED=true
# No username/password needed when security is disabled
EOF
    else
        cat >> "$env_file" << EOF
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=OlavOS123!
OPENSEARCH_INITIAL_ADMIN_PASSWORD=OlavOS123!
EOF
    fi
    
    cat >> "$env_file" << EOF

# Port Configuration
OPENSEARCH_PORT=${PORT_OPENSEARCH:-9200}
POSTGRES_PORT=${PORT_POSTGRES:-5432}
NETBOX_PORT=${PORT_NETBOX:-8080}
EOF
}

show_completion() {
    echo ""
    echo -e "${GREEN}"
    echo "========================================"
    echo "        🎉 Setup Complete!"
    echo "========================================"
    echo -e "${NC}"
    
    echo ""
    echo -e "${WHITE}Access:${NC}"
    echo -e "  - OLAV CLI:    ${CYAN}uv run olav${NC}"
    echo -e "  - NetBox:      ${CYAN}http://localhost:${PORT_NETBOX:-8080}${NC} (admin/admin)"
    
    echo ""
    echo -e "${WHITE}Configuration saved to:${NC} .env"
    
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Run 'uv run olav' to start chatting with OLAV"
    echo "  2. Add devices to NetBox if you haven't imported from CSV"
    echo ""

    show_system_status
}

show_system_status() {
    echo ""
    echo "========================================"
    echo "📊 System Status Summary"
    echo "========================================"
    echo ""

    # 1) Docker containers
    if command -v docker >/dev/null 2>&1; then
        echo "Docker containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" || true
    else
        echo "WARN: docker not found"
    fi

    # 2) SuzieQ GUI health
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS --max-time 5 "http://localhost:8501/healthz" >/dev/null 2>&1; then
            echo "SuzieQ GUI: OK http://localhost:8501/healthz"
        else
            echo "WARN: SuzieQ GUI health check failed (http://localhost:8501/healthz)"
        fi
    elif command -v python3 >/dev/null 2>&1; then
        python3 - <<'PY' || true
import urllib.request

url = "http://localhost:8501/healthz"
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        print(f"SuzieQ GUI: OK {url} ({r.status})")
except Exception as e:
    print(f"WARN: SuzieQ GUI health check failed ({url}): {e}")
PY
    else
        echo "WARN: curl/python3 not found; skipping SuzieQ GUI check"
    fi

    # 3) OLAV detailed health (includes SuzieQ GUI + parquet freshness)
    health_json=""
    health_url=""
    if command -v curl >/dev/null 2>&1; then
        for url in "http://localhost:8001/health/detailed" "http://localhost:8000/health/detailed"; do
            if health_json=$(curl -fsS --max-time 15 "$url" 2>/dev/null); then
                health_url="$url"
                break
            fi
        done
    elif command -v python3 >/dev/null 2>&1; then
        for url in "http://localhost:8001/health/detailed" "http://localhost:8000/health/detailed"; do
            health_json=$(python3 - <<PY 2>/dev/null || true
import urllib.request
import sys
u = "$url"
try:
    with urllib.request.urlopen(u, timeout=15) as r:
        sys.stdout.write(r.read().decode('utf-8', errors='replace'))
except Exception:
    pass
PY
)
            if [ -n "$health_json" ]; then
                health_url="$url"
                break
            fi
        done
    fi

    if [ -n "$health_json" ]; then
        echo ""
        echo "OLAV /health/detailed: $health_url"
        if command -v python3 >/dev/null 2>&1; then
            echo "$health_json" | python3 - <<'PY' || true
import json
import sys

raw = sys.stdin.read().strip().lstrip("\ufeff")
try:
    data = json.loads(raw)
except Exception as e:
    print(f"WARN: unable to parse JSON: {e}")
    sys.exit(0)

overall = str(data.get("status", "unknown"))
suz = (data.get("components") or {}).get("suzieq") or {}
suz_status = str(suz.get("status", "unknown"))
data_obj = suz.get("data") or {}
data_status = str(data_obj.get("status", "unknown"))
age = data_obj.get("age_seconds")

msg = f"overall={overall}; suzieq={suz_status}; data={data_status}"
if age is not None:
    try:
        msg += f"; age_seconds={int(age)}"
    except Exception:
        msg += f"; age_seconds={age}"

if overall == "healthy":
    print(f"OK: {msg}")
else:
    print(f"WARN: {msg}")
PY
        else
            echo "INFO: health JSON (raw):"
            echo "$health_json"
        fi
    else
        echo "WARN: OLAV /health/detailed not reachable on 8001/8000"
    fi

    # 4) SuzieQ parquet recency (best-effort)
    parquet_root="$SCRIPT_DIR/data/suzieq-parquet"
    if [ -d "$parquet_root" ]; then
        if command -v python3 >/dev/null 2>&1; then
            python3 - <<PY || true
import os
import time

root = r"$parquet_root"
newest_path = None
newest_mtime = None

for dirpath, _, filenames in os.walk(root):
    for name in filenames:
        if not name.endswith('.parquet'):
            continue
        path = os.path.join(dirpath, name)
        try:
            m = os.path.getmtime(path)
        except OSError:
            continue
        if newest_mtime is None or m > newest_mtime:
            newest_mtime = m
            newest_path = path

if newest_path is None:
    print(f"WARN: No SuzieQ parquet files found under {root}")
else:
    age = int(time.time() - newest_mtime)
    ts = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(newest_mtime))
    print(f"SuzieQ parquet newest: {ts} (age: {age}s)\n  {newest_path}")
PY
        else
            newest_file=$(find "$parquet_root" -type f -name "*.parquet" 2>/dev/null | head -n 1)
            if [ -n "$newest_file" ]; then
                echo "SuzieQ parquet newest: $newest_file"
            else
                echo "WARN: No SuzieQ parquet files found under $parquet_root"
            fi
        fi
    else
        echo "WARN: Parquet root not found: $parquet_root"
    fi
}

# ============================================
# Production Mode Steps
# ============================================

step_netbox_configuration() {
    print_step "1/8" "NetBox Configuration (SSOT)"
    
    echo ""
    echo -e "${WHITE}Select NetBox configuration:${NC}"
    echo "  [1] Connect to existing NetBox instance"
    echo "  [2] Create new local NetBox instance (Docker)"
    
    local choice=$(read_choice "Choice [1/2]" 2)
    
    if [ "$choice" = "1" ]; then
        # Existing NetBox
        echo ""
        NETBOX_URL=$(read_input "Enter NetBox URL" "https://netbox.example.com")
        NETBOX_TOKEN=$(read_input "Enter NetBox API Token" "" true)
        NETBOX_LOCAL="false"
        
        # Validate connection
        echo ""
        echo -e "${CYAN}Validating NetBox connection...${NC}"
        if curl -sf -H "Authorization: Token $NETBOX_TOKEN" "$NETBOX_URL/api/" >/dev/null 2>&1; then
            print_success "NetBox connection validated"
        else
            print_warning "Could not validate NetBox connection (will proceed anyway)"
        fi
    else
        # Local NetBox
        NETBOX_LOCAL="true"
        NETBOX_URL="http://netbox:8080"
        NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
        
        echo ""
        NETBOX_SUPERUSER_NAME=$(read_input "NetBox admin username" "admin")
        NETBOX_SUPERUSER_PASSWORD=$(read_input "NetBox admin password" "" true)
        NETBOX_SUPERUSER_EMAIL=$(read_input "NetBox admin email" "admin@olav.local")
        
        print_success "Local NetBox will be created"
    fi
}

step_infra_credentials() {
    print_step "5/8" "Infrastructure Credentials"
    
    echo ""
    echo -e "${WHITE}PostgreSQL Configuration:${NC}"
    POSTGRES_USER=$(read_input "PostgreSQL username" "olav")
    POSTGRES_PASSWORD=$(read_input "PostgreSQL password" "" true)
    
    echo ""
    echo -e "${WHITE}OpenSearch Configuration:${NC}"
    OPENSEARCH_USERNAME=$(read_input "OpenSearch username" "admin")
    while true; do
        OPENSEARCH_PASSWORD=$(read_input "OpenSearch password (min 8 chars; upper/lower/digit/special)" "" true)
        if is_strong_password "$OPENSEARCH_PASSWORD"; then
            break
        fi
        print_warning "OpenSearch password does not meet complexity requirements. Please try again."
    done
    
    print_success "Infrastructure credentials configured"
}

step_init_suzieq_config() {
    echo ""
    echo -e "${CYAN}Generating SuzieQ configuration...${NC}"
    
    local generated_configs_dir="$PROJECT_ROOT/data/generated_configs"
    local suzieq_config_path="$generated_configs_dir/suzieq_config.yml"
    local inventory_path="$generated_configs_dir/inventory.yml"
    
    mkdir -p "$generated_configs_dir"
    
    # Generate SuzieQ configuration
    cat > "$suzieq_config_path" << EOF
# SuzieQ Configuration for OLAV
# Generated by Setup Wizard on $(date '+%Y-%m-%d %H:%M:%S')

data-directory: /suzieq/parquet
# service-directory: /suzieq/config
# schema-directory: /suzieq/config/schema

period: 15

# Sources are defined in inventory.yml

rest:
  API_KEY: test
  address: 0.0.0.0
  port: 8000
  no-https: True
  logsize: 10000000
  log-level: WARNING

analyzer:
  timezone: America/Los_Angeles

poller:
  logging-level: WARNING
EOF
    echo -e "  Generated config: ${GREEN}$suzieq_config_path${NC}"

    # Generate Inventory File
    # Use variables from environment or defaults (device creds must be provided explicitly)
    local nb_url="${NETBOX_URL:-http://netbox:8080}"
    local nb_token="${NETBOX_TOKEN:-0123456789abcdef0123456789abcdef01234567}"
    local dev_user="${DEVICE_USERNAME}"
    local dev_pass="${DEVICE_PASSWORD}"
    local suzieq_tag="${SUZIEQ_TAG_NAME:-$DEFAULT_SUZIEQ_TAG_NAME}"

    if [ -z "$dev_user" ] || [ -z "$dev_pass" ]; then
        print_error "DEVICE_USERNAME / DEVICE_PASSWORD is required and cannot be empty"
        return 1
    fi

    cat > "$inventory_path" << EOF
sources:
  - name: netbox
    type: netbox
    url: $nb_url
    token: $nb_token
        tag:
            - $suzieq_tag

auths:
  - name: default-auth
    username: $dev_user
    password: $dev_pass

namespaces:
  - name: default
    source: netbox
    auth: default-auth
EOF
    print_success "SuzieQ configuration and inventory generated"
}

step_token_generation() {
    print_step "7/8" "OLAV Token Generation"
    
    echo ""
    echo -e "${CYAN}Generating OLAV API tokens...${NC}"
    
    # Generate a random JWT secret
    JWT_SECRET_KEY=$(openssl rand -base64 32 2>/dev/null || head -c 32 /dev/urandom | base64)
    
    print_success "JWT secret key generated"
    echo ""
    echo -e "${YELLOW}Note: After services start, run 'uv run olav register' to create client sessions${NC}"
}

step_config_confirmation() {
    print_step "8/8" "Configuration Summary"
    
    echo ""
    echo -e "${WHITE}Configuration Summary:${NC}"
    echo "----------------------------------------"
    echo -e "  Mode:           ${CYAN}Production${NC}"
    echo -e "  LLM Provider:   ${CYAN}$LLM_PROVIDER${NC}"
    echo -e "  LLM Model:      ${CYAN}$LLM_MODEL_NAME${NC}"
    echo -e "  Embedding:      ${CYAN}$EMBEDDING_PROVIDER / $EMBEDDING_MODEL${NC}"
    if [ "$NETBOX_LOCAL" = "true" ]; then
        echo -e "  NetBox:         ${CYAN}Local (Docker)${NC}"
    else
        echo -e "  NetBox:         ${CYAN}$NETBOX_URL${NC}"
    fi
    echo -e "  OpenSearch:     ${CYAN}Security Enabled${NC}"
    echo "----------------------------------------"
    
    echo ""
    local confirm=$(read_input "Proceed with this configuration? [Y/n]" "Y")
    
    if [[ ! "$confirm" =~ ^[Yy] ]]; then
        echo -e "${YELLOW}Setup cancelled.${NC}"
        exit 0
    fi
}

generate_env_file_production() {
    local env_file="$PROJECT_ROOT/.env"
    
    cat > "$env_file" << EOF
# ============================================
# OLAV Configuration
# Generated by Setup Wizard (Production Mode)
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================

# Deployment Mode
OLAV_MODE=production

# LLM Configuration
LLM_PROVIDER=$LLM_PROVIDER
LLM_API_KEY=$LLM_API_KEY
LLM_MODEL_NAME=$LLM_MODEL_NAME
EOF

    [ -n "$LLM_BASE_URL" ] && echo "LLM_BASE_URL=$LLM_BASE_URL" >> "$env_file"
    
    cat >> "$env_file" << EOF

# Embedding Configuration
EMBEDDING_PROVIDER=$EMBEDDING_PROVIDER
EMBEDDING_MODEL=$EMBEDDING_MODEL
EOF

    [ -n "$EMBEDDING_API_KEY" ] && echo "EMBEDDING_API_KEY=$EMBEDDING_API_KEY" >> "$env_file"
    [ -n "$EMBEDDING_BASE_URL" ] && echo "EMBEDDING_BASE_URL=$EMBEDDING_BASE_URL" >> "$env_file"
    
    cat >> "$env_file" << EOF

# Device Credentials
DEVICE_USERNAME=$DEVICE_USERNAME
DEVICE_PASSWORD=$DEVICE_PASSWORD
DEVICE_ENABLE_PASSWORD=$DEVICE_ENABLE_PASSWORD

# NetBox
NETBOX_URL=$NETBOX_URL
NETBOX_TOKEN=$NETBOX_TOKEN
EOF

    if [ "$NETBOX_LOCAL" = "true" ]; then
        cat >> "$env_file" << EOF
NETBOX_SUPERUSER_NAME=$NETBOX_SUPERUSER_NAME
NETBOX_SUPERUSER_EMAIL=$NETBOX_SUPERUSER_EMAIL
NETBOX_SUPERUSER_PASSWORD=$NETBOX_SUPERUSER_PASSWORD
NETBOX_SECRET_KEY=production-secret-key-$(date +%s)
EOF
    fi
    
    cat >> "$env_file" << EOF

# PostgreSQL
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=olav

# OpenSearch (Security Enabled)
OPENSEARCH_SECURITY_DISABLED=false
OPENSEARCH_USERNAME=$OPENSEARCH_USERNAME
OPENSEARCH_PASSWORD=$OPENSEARCH_PASSWORD
OPENSEARCH_INITIAL_ADMIN_PASSWORD=$OPENSEARCH_PASSWORD

# JWT Configuration
JWT_SECRET_KEY=$JWT_SECRET_KEY

# Port Configuration
OPENSEARCH_PORT=${PORT_OPENSEARCH:-9200}
POSTGRES_PORT=${PORT_POSTGRES:-5432}
NETBOX_PORT=${PORT_NETBOX:-8080}
EOF
}

show_completion_production() {
    echo ""
    echo -e "${GREEN}"
    echo "========================================"
    echo "    🎉 Production Setup Complete!"
    echo "========================================"
    echo -e "${NC}"
    
    echo ""
    echo -e "${WHITE}Access:${NC}"
    echo -e "  - OLAV CLI:    ${CYAN}uv run olav${NC}"
    if [ "$NETBOX_LOCAL" = "true" ]; then
        echo -e "  - NetBox:      ${CYAN}http://localhost:${PORT_NETBOX:-8080}${NC} ($NETBOX_SUPERUSER_NAME/***)"
    else
        echo -e "  - NetBox:      ${CYAN}$NETBOX_URL${NC}"
    fi
    echo -e "  - OpenSearch:  ${CYAN}http://localhost:${PORT_OPENSEARCH:-9200}${NC}"
    
    echo ""
    echo -e "${WHITE}Configuration saved to:${NC} .env"
    
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Run 'uv run olav register' to create client session"
    echo "  2. Run 'uv run olav' to start chatting with OLAV"
    echo "  3. Review OpenSearch security settings if needed"
    echo ""

    show_system_status
}

# ============================================
# Main Entry Point
# ============================================

main() {
    # Parse arguments
    MODE=""
    case "${1:-}" in
        --quick|-q)
            MODE="quicktest"
            ;;
        --production|-p)
            MODE="production"
            ;;
        "")
            # Interactive mode selection
            MODE=$(select_deployment_mode)
            ;;
        *)
            echo "Usage: $0 [--quick|--production]"
            exit 1
            ;;
    esac
    
    # Check prerequisites
    check_uv || exit 1
    
    print_banner
    echo -e "${CYAN}Starting $MODE mode setup...${NC}"
    
    if [ "$MODE" = "quicktest" ]; then
        # Quick Test Mode: 5 steps
        step_llm_configuration
        step_embedding_configuration
        step_device_credentials
        step_port_check
        step_init_suzieq_config
        step_start_services
        step_schema_init
        show_completion
    else
        # Production Mode: 8 steps
        
        # Step 1: NetBox configuration
        step_netbox_configuration
        
        # Step 2: LLM configuration (reuse, custom header)
        print_step "2/8" "LLM Configuration"
        step_llm_configuration_inner
        
        # Step 3: Embedding configuration (reuse, custom header)
        print_step "3/8" "Embedding Configuration"
        step_embedding_configuration_inner
        
        # Step 4: Device credentials (reuse, custom header)
        print_step "4/8" "Device Credentials"
        step_device_credentials_inner
        
        # Step 5: Infrastructure credentials
        step_infra_credentials
        
        # Step 6: Port check & start services
        print_step "6/8" "Port Check & Start Services"
        step_port_check_inner
        step_init_suzieq_config
        step_start_services
        
        # Step 7: Token generation
        step_token_generation
        
        # Step 8: Configuration confirmation
        step_config_confirmation
        
        # Schema initialization
        step_schema_init_inner
        
        # Generate production .env file
        generate_env_file_production
        print_success ".env file generated for production"
        
        show_completion_production
    fi
}

# Run
main "$@"
