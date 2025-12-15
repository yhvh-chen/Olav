#!/usr/bin/env bash
#
# OLAV Setup Wizard for Linux/macOS
# Interactive wizard to configure and start OLAV (NetAIChatOps).
#
# Usage:
#   ./setup-wizard.sh           # Interactive mode selection
#   ./setup-wizard.sh --quick   # Quick Test mode
#   ./setup-wizard.sh --production  # Production mode
#

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
DEFAULT_DEVICE_USERNAME="admin"
DEFAULT_DEVICE_PASSWORD="admin"

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
        2) LLM_PROVIDER="openai_compatible" ;;
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
        LLM_BASE_URL=$(read_input "Enter API Endpoint" "$default_endpoint")
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
    DEVICE_USERNAME=$(read_input "Enter device username" "admin")
    DEVICE_PASSWORD=$(read_input "Enter device password" "" "true")
    
    echo ""
    local enable_password=$(read_input "Enter enable password (Enter if same as device password)" "" "true")
    if [ -z "$enable_password" ]; then
        DEVICE_ENABLE_PASSWORD="$DEVICE_PASSWORD"
    else
        DEVICE_ENABLE_PASSWORD="$enable_password"
    fi
    
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
    echo -e "${CYAN}Starting Docker containers...${NC}"
    
    # Check Docker
    if ! check_docker; then
        exit 1
    fi
    
    # Only generate env file in Quick Test mode (Production mode generates its own)
    if [ "$MODE" = "quicktest" ]; then
        generate_env_file
        print_success ".env file generated"
    fi
    
    # Start containers
    cd "$PROJECT_ROOT"
    if docker-compose --profile netbox up -d; then
        print_success "Docker containers started"
    else
        print_error "Failed to start containers"
        exit 1
    fi
    
    # Wait for services
    echo ""
    echo -e "${CYAN}Waiting for services to be healthy... (this may take 60-90 seconds)${NC}"
    
    local retries=12
    local healthy=false
    while [ $retries -gt 0 ] && [ "$healthy" = "false" ]; do
        sleep 5
        echo -n "."
        
        # Simple health check - just verify containers are running
        local running=$(docker-compose ps --format json 2>/dev/null | grep -c '"running"' || echo "0")
        if [ "$running" -ge 3 ]; then
            healthy=true
        fi
        retries=$((retries - 1))
    done
    
    echo ""
    if [ "$healthy" = "true" ]; then
        print_success "All core services are ready"
    else
        print_warning "Some services may still be starting. Check with 'docker-compose ps'"
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
        
        # Prompt user - default YES
        local import_devices=$(read_input "Import devices from inventory.csv? [Y/n]" "Y")
        
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

# NetBox (auto-created local instance)
NETBOX_URL=http://netbox:8080
NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567
NETBOX_SUPERUSER_NAME=admin
NETBOX_SUPERUSER_EMAIL=admin@olav.local
NETBOX_SUPERUSER_PASSWORD=admin
NETBOX_SECRET_KEY=setup-wizard-generated-key-$(date +%s)

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
    OPENSEARCH_PASSWORD=$(read_input "OpenSearch password" "" true)
    
    print_success "Infrastructure credentials configured"
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
