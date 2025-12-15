#Requires -Version 5.1
<#
.SYNOPSIS
    OLAV Setup Wizard for Windows
.DESCRIPTION
    Interactive wizard to configure and start OLAV (NetAIChatOps).
    Supports Quick Test mode (minimal config) and Production mode (full wizard).
.PARAMETER Mode
    Deployment mode: QuickTest or Production
.EXAMPLE
    .\setup-wizard.ps1
    .\setup-wizard.ps1 -Mode QuickTest
    .\setup-wizard.ps1 -Mode Production
#>

[CmdletBinding()]
param(
    [ValidateSet("QuickTest", "Production", "")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"

# ============================================
# Configuration
# ============================================

$script:CONFIG = @{
    # LLM Providers
    LLM_PROVIDERS = @(
        @{ Id = 1; Name = "OpenAI"; RequiresKey = $true; RequiresEndpoint = $false }
        @{ Id = 2; Name = "OpenAI Compatible"; RequiresKey = $true; RequiresEndpoint = $true }
        @{ Id = 3; Name = "Azure OpenAI"; RequiresKey = $true; RequiresEndpoint = $true }
        @{ Id = 4; Name = "Anthropic"; RequiresKey = $true; RequiresEndpoint = $false }
        @{ Id = 5; Name = "Google AI"; RequiresKey = $true; RequiresEndpoint = $false }
        @{ Id = 6; Name = "Ollama (local)"; RequiresKey = $false; RequiresEndpoint = $true }
    )
    
    # Embedding Providers
    EMBEDDING_PROVIDERS = @(
        @{ Id = 1; Name = "OpenAI (same API Key)"; RequiresKey = $false }
        @{ Id = 2; Name = "OpenAI (different API Key)"; RequiresKey = $true }
        @{ Id = 3; Name = "Azure OpenAI"; RequiresKey = $true }
        @{ Id = 4; Name = "Ollama (local)"; RequiresKey = $false }
    )
    
    # Default Ports (matching docker-compose port mappings)
    PORTS = @{
        OpenSearch = 19200
        PostgreSQL = 55432
        NetBox     = 8080
        OlavAPI    = 8000
    }
    
    # Alternative Ports (when default is in use)
    ALT_PORTS = @{
        19200 = 29200
        55432 = 65432
        8080 = 8081
        8000 = 8001
    }
    
    # Default Credentials (Quick Test)
    DEFAULTS = @{
        POSTGRES_USER     = "olav"
        POSTGRES_PASSWORD = "olav"
        NETBOX_USER       = "admin"
        NETBOX_PASSWORD   = "admin"
        DEVICE_USERNAME   = "admin"
        DEVICE_PASSWORD   = "admin"
    }
}

# ============================================
# Helper Functions
# ============================================

function Write-Banner {
    Clear-Host
    Write-Host @"
========================================
       OLAV Setup Wizard v1.0
========================================
"@ -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Step, [string]$Title)
    Write-Host ""
    Write-Host "[$Step] $Title" -ForegroundColor Yellow
    Write-Host ("-" * 40)
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠️ $Message" -ForegroundColor Yellow
}

function Read-UserInput {
    param(
        [string]$Prompt,
        [string]$Default = "",
        [switch]$IsPassword
    )
    
    $displayPrompt = if ($Default) { "$Prompt [$Default]: " } else { "${Prompt}: " }
    
    if ($IsPassword) {
        $secureString = Read-Host -Prompt $displayPrompt -AsSecureString
        $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureString)
        $plainText = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)
        
        if ([string]::IsNullOrEmpty($plainText) -and $Default) {
            return $Default
        }
        return $plainText
    }
    else {
        $input = Read-Host -Prompt $displayPrompt
        if ([string]::IsNullOrEmpty($input) -and $Default) {
            return $Default
        }
        return $input
    }
}

function Read-Choice {
    param(
        [string]$Prompt,
        [int]$Min = 1,
        [int]$Max
    )
    
    while ($true) {
        $input = Read-Host -Prompt $Prompt
        if ($input -match '^\d+$') {
            $choice = [int]$input
            if ($choice -ge $Min -and $choice -le $Max) {
                return $choice
            }
        }
        Write-Host "Please enter a number between $Min and $Max" -ForegroundColor Yellow
    }
}

function Test-PortAvailable {
    param([int]$Port)
    
    try {
        $connection = New-Object System.Net.Sockets.TcpClient
        $connection.Connect("127.0.0.1", $Port)
        $connection.Close()
        return $false  # Port is in use
    }
    catch {
        return $true   # Port is available
    }
}

function Get-ProcessUsingPort {
    param([int]$Port)
    
    $netstat = netstat -ano | Select-String ":$Port\s" | Select-Object -First 1
    if ($netstat) {
        $parts = $netstat.Line -split '\s+'
        $pid = $parts[-1]
        if ($pid -match '^\d+$') {
            $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($process) {
                return @{
                    PID = $pid
                    Name = $process.ProcessName
                }
            }
            return @{ PID = $pid; Name = "Unknown" }
        }
    }
    return $null
}

function Test-DockerRunning {
    try {
        $null = docker info 2>&1
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Test-LLMConnection {
    param(
        [string]$Provider,
        [string]$ApiKey,
        [string]$Model,
        [string]$Endpoint = ""
    )
    
    Write-Host "Testing LLM connection..." -ForegroundColor Cyan
    
    # For Ollama, check if server is running
    if ($Provider -eq "ollama") {
        try {
            $response = Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec 5
            return $true
        }
        catch {
            return $false
        }
    }
    
    # For API-based providers, do a simple test
    # This is a placeholder - actual implementation would call the LLM
    if ([string]::IsNullOrEmpty($ApiKey)) {
        return $false
    }
    
    # Basic API key format validation
    switch ($Provider) {
        "openai" { return $ApiKey -match '^sk-' }
        "anthropic" { return $ApiKey -match '^sk-ant-' }
        default { return $ApiKey.Length -gt 10 }
    }
}

# ============================================
# Main Wizard Steps
# ============================================

function Select-DeploymentMode {
    Write-Banner
    
    Write-Host @"

Select deployment mode:

  [1] Quick Test
      - Minimal configuration (5 steps)
      - All infrastructure uses default credentials
      - OpenSearch security disabled
      - Best for: Evaluation, development, demos

  [2] Production
      - Full configuration wizard (8 steps)
      - Custom credentials for all services
      - OpenSearch security enabled
      - Best for: Production, multi-user environments

"@ -ForegroundColor White

    $choice = Read-Choice -Prompt "Choice [1/2]" -Max 2
    return if ($choice -eq 1) { "QuickTest" } else { "Production" }
}

function Step-LLMConfiguration {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "1/7" -Title "LLM Configuration"
    }
    
    Write-Host ""
    Write-Host "Select LLM Provider:" -ForegroundColor White
    foreach ($provider in $script:CONFIG.LLM_PROVIDERS) {
        Write-Host "  [$($provider.Id)] $($provider.Name)"
    }
    
    $choice = Read-Choice -Prompt "Choice [1-6]" -Max 6
    $provider = $script:CONFIG.LLM_PROVIDERS | Where-Object { $_.Id -eq $choice }
    
    $Config.LLM_PROVIDER = switch ($choice) {
        1 { "openai" }
        2 { "openai_compatible" }
        3 { "azure" }
        4 { "anthropic" }
        5 { "google" }
        6 { "ollama" }
    }
    
    # API Key
    if ($provider.RequiresKey) {
        Write-Host ""
        $Config.LLM_API_KEY = Read-UserInput -Prompt "Enter API Key" -IsPassword
    }
    
    # Endpoint (for Azure, Ollama, OpenAI Compatible)
    if ($provider.RequiresEndpoint) {
        $defaultEndpoint = if ($choice -eq 6) { "http://host.docker.internal:11434" } else { "" }
        $Config.LLM_BASE_URL = Read-UserInput -Prompt "Enter API Endpoint" -Default $defaultEndpoint
    }
    
    # Model name
    Write-Host ""
    $Config.LLM_MODEL_NAME = Read-UserInput -Prompt "Enter model name (e.g. gpt-4o, claude-3-opus)"
    
    # Test connection
    Write-Host ""
    $testResult = Test-LLMConnection -Provider $Config.LLM_PROVIDER -ApiKey $Config.LLM_API_KEY -Model $Config.LLM_MODEL_NAME -Endpoint $Config.LLM_BASE_URL
    
    if ($testResult) {
        Write-Success "LLM configuration validated"
    }
    else {
        Write-Warning "Could not validate LLM connection (will proceed anyway)"
    }
}

function Step-EmbeddingConfiguration {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "2/7" -Title "Embedding Configuration"
    }
    
    Write-Host ""
    Write-Host "Select Embedding Provider:" -ForegroundColor White
    foreach ($provider in $script:CONFIG.EMBEDDING_PROVIDERS) {
        Write-Host "  [$($provider.Id)] $($provider.Name)"
    }
    
    $choice = Read-Choice -Prompt "Choice [1-4]" -Max 4
    
    switch ($choice) {
        1 {
            # Same as LLM (OpenAI)
            $Config.EMBEDDING_PROVIDER = "openai"
            $Config.EMBEDDING_API_KEY = $Config.LLM_API_KEY
        }
        2 {
            # Different OpenAI key
            $Config.EMBEDDING_PROVIDER = "openai"
            $Config.EMBEDDING_API_KEY = Read-UserInput -Prompt "Enter Embedding API Key" -IsPassword
        }
        3 {
            # Azure
            $Config.EMBEDDING_PROVIDER = "azure"
            $Config.EMBEDDING_API_KEY = Read-UserInput -Prompt "Enter Azure Embedding API Key" -IsPassword
            $Config.EMBEDDING_BASE_URL = Read-UserInput -Prompt "Enter Azure Embedding Endpoint"
        }
        4 {
            # Ollama
            $Config.EMBEDDING_PROVIDER = "ollama"
            $Config.EMBEDDING_BASE_URL = Read-UserInput -Prompt "Enter Ollama Endpoint" -Default "http://host.docker.internal:11434"
        }
    }
    
    # Embedding model
    $defaultModel = if ($Config.EMBEDDING_PROVIDER -eq "openai") { "text-embedding-3-small" } else { "" }
    $Config.EMBEDDING_MODEL = Read-UserInput -Prompt "Enter Embedding model name" -Default $defaultModel
    
    Write-Success "Embedding configuration complete"
}

function Step-DeviceCredentials {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "3/7" -Title "Device Credentials (SSH/NETCONF access)"
    }
    
    Write-Host ""
    $Config.DEVICE_USERNAME = Read-UserInput -Prompt "Enter device username" -Default "admin"
    $Config.DEVICE_PASSWORD = Read-UserInput -Prompt "Enter device password" -IsPassword
    
    Write-Host ""
    $enablePassword = Read-UserInput -Prompt "Enter enable password (Enter if same as device password)" -IsPassword
    if ([string]::IsNullOrEmpty($enablePassword)) {
        $Config.DEVICE_ENABLE_PASSWORD = $Config.DEVICE_PASSWORD
    }
    else {
        $Config.DEVICE_ENABLE_PASSWORD = $enablePassword
    }
    
    Write-Success "Device credentials configured"
}

function Step-PortCheck {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "4/7" -Title "Port Availability Check"
    }
    
    Write-Host ""
    Write-Host "Checking required ports..." -ForegroundColor Cyan
    
    $portsToCheck = @{
        "OpenSearch" = $script:CONFIG.PORTS.OpenSearch
        "PostgreSQL" = $script:CONFIG.PORTS.PostgreSQL
        "NetBox"     = $script:CONFIG.PORTS.NetBox
    }
    
    $portConfig = @{}
    $hasConflicts = $false
    
    foreach ($service in $portsToCheck.Keys) {
        $port = $portsToCheck[$service]
        $available = Test-PortAvailable -Port $port
        
        if ($available) {
            Write-Host "  - $service ($port): " -NoNewline
            Write-Host "✅ Available" -ForegroundColor Green
            $portConfig[$service] = $port
        }
        else {
            $hasConflicts = $true
            $processInfo = Get-ProcessUsingPort -Port $port
            Write-Host "  - $service ($port): " -NoNewline
            Write-Host "⚠️ In use" -ForegroundColor Yellow -NoNewline
            if ($processInfo) {
                Write-Host " (Process: $($processInfo.Name) PID $($processInfo.PID))" -ForegroundColor Yellow
            }
            else {
                Write-Host ""
            }
            
            # Offer alternative
            $altPort = $script:CONFIG.ALT_PORTS[$port]
            if (-not $altPort) { $altPort = $port + 1 }
            
            $useAlt = Read-UserInput -Prompt "  Use alternative port $altPort? [Y/n]" -Default "Y"
            if ($useAlt -match '^[Yy]') {
                $portConfig[$service] = $altPort
                Write-Host "  → $service will use port $altPort" -ForegroundColor Cyan
            }
            else {
                $portConfig[$service] = $port
                Write-Warning "  → Keeping port $port (may fail to start)"
            }
        }
    }
    
    # Save port config
    $Config.OPENSEARCH_PORT = $portConfig["OpenSearch"]
    $Config.POSTGRES_PORT = $portConfig["PostgreSQL"]
    $Config.NETBOX_PORT = $portConfig["NetBox"]
    
    Write-Host ""
    Write-Success "Port check complete"
}

function Step-StartNetBox {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "5/7" -Title "Starting NetBox"
    }
    
    Write-Host ""
    Write-Host "Starting NetBox containers (required for inventory setup)..." -ForegroundColor Cyan
    
    # Check Docker
    if (-not (Test-DockerRunning)) {
        Write-Error "Docker is not running. Please start Docker Desktop and try again."
        exit 1
    }
    
    # Generate .env file first
    $envContent = Generate-EnvFile -Config $Config
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $envPath = Join-Path $projectRoot ".env"
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8
    Write-Success ".env file generated"
    
    # Start only NetBox related containers
    Push-Location $projectRoot
    try {
        $env:COMPOSE_DOCKER_CLI_BUILD = "0"
        
        # Start NetBox dependencies first
        Write-Host "  Starting NetBox PostgreSQL..." -ForegroundColor Gray
        & docker-compose up -d netbox-postgres netbox-redis netbox-redis-cache 2>&1 | Out-Null
        Start-Sleep -Seconds 5
        
        # Then start NetBox itself
        Write-Host "  Starting NetBox..." -ForegroundColor Gray
        & docker-compose --profile netbox up -d netbox 2>&1 | Out-Null
        
        # Wait for NetBox to be healthy
        Write-Host ""
        Write-Host "Waiting for NetBox to be healthy... (this may take 60-120 seconds)" -ForegroundColor Cyan
        
        $retries = 24  # 2 minutes
        $healthy = $false
        while ($retries -gt 0 -and -not $healthy) {
            $status = docker inspect --format='{{.State.Health.Status}}' olav-netbox 2>$null
            if ($status -eq "healthy") {
                $healthy = $true
            }
            else {
                Start-Sleep -Seconds 5
                $retries--
                Write-Host "." -NoNewline
            }
        }
        
        Write-Host ""
        if ($healthy) {
            Write-Success "NetBox is healthy and ready"
        }
        else {
            Write-Warning "NetBox may still be starting. Proceeding anyway..."
        }
    }
    finally {
        Pop-Location
    }
}

function Step-NetBoxInventoryInit {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "6/7" -Title "NetBox Inventory Setup"
    }
    
    Write-Host ""
    Write-Host "Initializing NetBox with device inventory..." -ForegroundColor Cyan
    
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $defaultCsv = Join-Path $projectRoot "config\inventory.csv"
    
    # Check if inventory.csv exists
    if (Test-Path $defaultCsv) {
        # Count devices in CSV
        $deviceCount = (Get-Content $defaultCsv | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | Measure-Object).Count - 1
        Write-Host "  Found inventory.csv with $deviceCount device(s)" -ForegroundColor Gray
        
        $importNow = Read-UserInput -Prompt "Import devices from inventory.csv? [Y/n]" -Default "Y"
        
        if ($importNow -match '^[Yy]') {
            Write-Host ""
            Write-Host "Importing devices to NetBox..." -ForegroundColor Cyan
            
            # Run the netbox_ingest.py script
            Push-Location $projectRoot
            try {
                $env:NETBOX_URL = "http://localhost:$($Config.NETBOX_PORT)"
                $env:NETBOX_TOKEN = "0123456789abcdef0123456789abcdef01234567"
                
                $result = & uv run python scripts/netbox_ingest.py 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Device inventory imported successfully"
                }
                elseif ($LASTEXITCODE -eq 99) {
                    Write-Success "NetBox already has devices (skipped import)"
                }
                else {
                    Write-Warning "Import had issues: $result"
                }
            }
            finally {
                Pop-Location
            }
        }
        else {
            Write-Host "  Skipping device import" -ForegroundColor Gray
        }
    }
    else {
        Write-Host "  No inventory.csv found at: $defaultCsv" -ForegroundColor Yellow
        Write-Host "  You can import devices later with: uv run olav init netbox --csv <path>" -ForegroundColor Gray
    }
}

function Step-StartRemainingServices {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "7/7" -Title "Starting Remaining Services"
    }
    
    Write-Host ""
    Write-Host "Starting OLAV core services..." -ForegroundColor Cyan
    
    $projectRoot = Split-Path -Parent $PSScriptRoot
    
    Push-Location $projectRoot
    try {
        $env:COMPOSE_DOCKER_CLI_BUILD = "0"
        
        # Start remaining services (OpenSearch, PostgreSQL, olav-server, olav-app, etc.)
        & docker-compose --profile netbox up -d 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $_.Exception.Message -ForegroundColor Gray
            } else {
                Write-Host $_ -ForegroundColor Gray
            }
        }
        
        # Wait for core services
        Write-Host ""
        Write-Host "Waiting for services to be healthy..." -ForegroundColor Cyan
        Start-Sleep -Seconds 20
        
        $retries = 12
        $healthy = $false
        while ($retries -gt 0 -and -not $healthy) {
            $runningContainers = docker ps --filter "name=olav" --format "{{.Names}}: {{.Status}}" 2>$null
            $healthyCount = ($runningContainers | Where-Object { $_ -match "healthy" }).Count
            $totalContainers = ($runningContainers | Measure-Object).Count
            
            if ($totalContainers -ge 5 -and $healthyCount -ge 4) {
                $healthy = $true
            }
            else {
                Start-Sleep -Seconds 5
                $retries--
                Write-Host "." -NoNewline
            }
        }
        
        Write-Host ""
        if ($healthy) {
            Write-Success "All core services are ready"
        }
        else {
            Write-Warning "Some services may still be starting. Check with 'docker ps'"
        }
    }
    finally {
        Pop-Location
    }
}

function Step-StartServices {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    Write-Host ""
    Write-Host "Starting Docker containers..." -ForegroundColor Cyan
    
    # Check Docker
    if (-not (Test-DockerRunning)) {
        Write-Error "Docker is not running. Please start Docker Desktop and try again."
        exit 1
    }
    
    # Generate .env file
    $envContent = Generate-EnvFile -Config $Config
    $projectRoot = Split-Path -Parent $PSScriptRoot
    $envPath = Join-Path $projectRoot ".env"
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8
    Write-Success ".env file generated"
    
    # Start containers - use Push-Location to change directory
    $composeFile = Join-Path $projectRoot "docker-compose.yml"
    Push-Location $projectRoot
    try {
        # Redirect stderr to stdout to avoid PowerShell treating progress as errors
        $env:COMPOSE_DOCKER_CLI_BUILD = "0"
        & docker-compose --profile netbox up -d 2>&1 | ForEach-Object { 
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $_.Exception.Message -ForegroundColor Gray
            } else {
                Write-Host $_ -ForegroundColor Gray
            }
        }
        
        # Check if containers are running
        $runningCount = (docker ps --filter "name=olav" -q | Measure-Object).Count
        if ($runningCount -ge 2) {
            Write-Success "Docker containers started"
        }
        else {
            Write-Error "Failed to start containers. Check docker-compose logs."
            exit 1
        }
    }
    finally {
        Pop-Location
    }
    
    # Wait for services
    Write-Host ""
    Write-Host "Waiting for services to be healthy... (this may take 60-90 seconds)" -ForegroundColor Cyan
    Start-Sleep -Seconds 30
    
    # Check health using docker ps
    $retries = 12
    $healthy = $false
    while ($retries -gt 0 -and -not $healthy) {
        # Use docker ps to check container status
        $runningContainers = docker ps --filter "name=olav" --format "{{.Names}}: {{.Status}}" 2>$null
        $healthyCount = ($runningContainers | Where-Object { $_ -match "healthy" }).Count
        $totalContainers = ($runningContainers | Measure-Object).Count
        
        if ($totalContainers -ge 3 -and $healthyCount -ge 2) {
            $healthy = $true
        }
        else {
            Start-Sleep -Seconds 5
            $retries--
            Write-Host "." -NoNewline
        }
    }
    
    Write-Host ""
    if ($healthy) {
        Write-Success "All core services are ready"
    }
    else {
        Write-Warning "Some services may still be starting. Check with 'docker ps'"
    }
}

function Step-SchemaInit {
    param(
        [hashtable]$Config,
        [switch]$SkipHeader
    )
    
    if (-not $SkipHeader) {
        Write-Step -Step "8/8" -Title "Schema Initialization"
    }
    
    Write-Host ""
    Write-Host "Initializing schemas..." -ForegroundColor Cyan
    
    # Run init command
    $initResult = & uv run olav init all 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Schema initialization complete"
    }
    else {
        Write-Warning "Schema initialization had issues: $initResult"
    }
    
    # Custom CSV Import (optional - for users with non-standard paths)
    # Note: Default inventory.csv is already imported in Step-NetBoxInventoryInit
    Write-Host ""
    $importCsv = Read-UserInput -Prompt "Import devices from custom CSV? [y/N]" -Default "N"
    
    if ($importCsv -match '^[Yy]') {
        $csvPath = Read-UserInput -Prompt "Enter CSV file path" -Default ""
        
        if ($csvPath -and (Test-Path $csvPath)) {
            # Use direct Python call instead of broken CLI parameter
            $projectRoot = Split-Path -Parent $PSScriptRoot
            Push-Location $projectRoot
            try {
                $env:NETBOX_URL = "http://localhost:$($Config.NETBOX_PORT)"
                $env:NETBOX_TOKEN = "0123456789abcdef0123456789abcdef01234567"
                $env:NETBOX_INGEST_FORCE = "true"
                
                Write-Host ""
                Write-Host "Importing custom CSV..." -ForegroundColor Cyan
                
                $importResult = & uv run python scripts/netbox_ingest.py 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "Custom device import complete"
                }
                elseif ($LASTEXITCODE -eq 99) {
                    Write-Success "NetBox already has devices (skipped custom import)"
                }
                else {
                    Write-Warning "Custom device import had issues: $importResult"
                }
            }
            finally {
                Pop-Location
            }
        }
        elseif ($csvPath) {
            Write-Warning "CSV file not found: $csvPath"
        }
        else {
            Write-Host "No CSV file path provided"
        }
    }
}

function Generate-EnvFile {
    param([hashtable]$Config)
    
    $envLines = @(
        "# ============================================"
        "# OLAV Configuration"
        "# Generated by Setup Wizard ($(if ($Config.Mode -eq 'QuickTest') { 'Quick Test' } else { 'Production' }) Mode)"
        "# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "# ============================================"
        ""
        "# Deployment Mode"
        "OLAV_MODE=$($Config.Mode.ToLower())"
        ""
        "# LLM Configuration"
        "LLM_PROVIDER=$($Config.LLM_PROVIDER)"
        "LLM_API_KEY=$($Config.LLM_API_KEY)"
        "LLM_MODEL_NAME=$($Config.LLM_MODEL_NAME)"
    )
    
    if ($Config.LLM_BASE_URL) {
        $envLines += "LLM_BASE_URL=$($Config.LLM_BASE_URL)"
    }
    
    $envLines += @(
        ""
        "# Embedding Configuration"
        "EMBEDDING_PROVIDER=$($Config.EMBEDDING_PROVIDER)"
        "EMBEDDING_MODEL=$($Config.EMBEDDING_MODEL)"
    )
    
    if ($Config.EMBEDDING_API_KEY) {
        $envLines += "EMBEDDING_API_KEY=$($Config.EMBEDDING_API_KEY)"
    }
    
    if ($Config.EMBEDDING_BASE_URL) {
        $envLines += "EMBEDDING_BASE_URL=$($Config.EMBEDDING_BASE_URL)"
    }
    
    $envLines += @(
        ""
        "# Device Credentials"
        "DEVICE_USERNAME=$($Config.DEVICE_USERNAME)"
        "DEVICE_PASSWORD=$($Config.DEVICE_PASSWORD)"
        "DEVICE_ENABLE_PASSWORD=$($Config.DEVICE_ENABLE_PASSWORD)"
        ""
        "# NetBox (auto-created local instance)"
        "NETBOX_URL=http://netbox:8080"
        "NETBOX_TOKEN=0123456789abcdef0123456789abcdef01234567"
        "NETBOX_SUPERUSER_NAME=admin"
        "NETBOX_SUPERUSER_EMAIL=admin@olav.local"
        "NETBOX_SUPERUSER_PASSWORD=admin"
        "NETBOX_SECRET_KEY=setup-wizard-generated-key-$(Get-Random)"
        ""
        "# PostgreSQL"
        "POSTGRES_USER=$($script:CONFIG.DEFAULTS.POSTGRES_USER)"
        "POSTGRES_PASSWORD=$($script:CONFIG.DEFAULTS.POSTGRES_PASSWORD)"
        "POSTGRES_DB=olav"
        ""
        "# OpenSearch"
    )
    
    if ($Config.Mode -eq "QuickTest") {
        $envLines += @(
            "OPENSEARCH_SECURITY_DISABLED=true"
            "# No username/password needed when security is disabled"
        )
    }
    else {
        $envLines += @(
            "OPENSEARCH_SECURITY_DISABLED=false"
            "OPENSEARCH_USERNAME=$($Config.OPENSEARCH_USERNAME)"
            "OPENSEARCH_PASSWORD=$($Config.OPENSEARCH_PASSWORD)"
        )
    }
    
    $envLines += @(
        ""
        "# Port Configuration"
        "OPENSEARCH_PORT=$($Config.OPENSEARCH_PORT)"
        "POSTGRES_PORT=$($Config.POSTGRES_PORT)"
        "NETBOX_PORT=$($Config.NETBOX_PORT)"
    )
    
    return $envLines -join "`n"
}

# ============================================
# Production Mode Steps
# ============================================

function Step-NetBoxConfiguration {
    param([hashtable]$Config)
    
    Write-Step -Step "1/8" -Title "NetBox Configuration (SSOT)"
    
    Write-Host ""
    Write-Host "Select NetBox configuration:" -ForegroundColor White
    Write-Host "  [1] Connect to existing NetBox instance"
    Write-Host "  [2] Create new local NetBox instance (Docker)"
    
    $choice = Read-Choice -Prompt "Choice [1/2]" -Max 2
    
    if ($choice -eq 1) {
        # Existing NetBox
        Write-Host ""
        $Config.NETBOX_URL = Read-UserInput -Prompt "Enter NetBox URL" -Default "https://netbox.example.com"
        $Config.NETBOX_TOKEN = Read-UserInput -Prompt "Enter NetBox API Token" -IsPassword
        $Config.NETBOX_LOCAL = $false
        
        # Validate connection
        Write-Host ""
        Write-Host "Validating NetBox connection..." -ForegroundColor Cyan
        try {
            $headers = @{ "Authorization" = "Token $($Config.NETBOX_TOKEN)" }
            $response = Invoke-RestMethod -Uri "$($Config.NETBOX_URL)/api/" -Headers $headers -TimeoutSec 10
            Write-Success "NetBox connection validated"
        }
        catch {
            Write-Warning "Could not validate NetBox connection (will proceed anyway)"
        }
    }
    else {
        # Local NetBox
        $Config.NETBOX_LOCAL = $true
        $Config.NETBOX_URL = "http://netbox:8080"
        $Config.NETBOX_TOKEN = "0123456789abcdef0123456789abcdef01234567"
        
        Write-Host ""
        $Config.NETBOX_SUPERUSER_NAME = Read-UserInput -Prompt "NetBox admin username" -Default "admin"
        $Config.NETBOX_SUPERUSER_PASSWORD = Read-UserInput -Prompt "NetBox admin password" -IsPassword
        $Config.NETBOX_SUPERUSER_EMAIL = Read-UserInput -Prompt "NetBox admin email" -Default "admin@olav.local"
        
        Write-Success "Local NetBox will be created"
    }
}

function Step-InfraCredentials {
    param([hashtable]$Config)
    
    Write-Step -Step "5/8" -Title "Infrastructure Credentials"
    
    Write-Host ""
    Write-Host "PostgreSQL Configuration:" -ForegroundColor White
    $Config.POSTGRES_USER = Read-UserInput -Prompt "PostgreSQL username" -Default "olav"
    $Config.POSTGRES_PASSWORD = Read-UserInput -Prompt "PostgreSQL password" -IsPassword
    
    Write-Host ""
    Write-Host "OpenSearch Configuration:" -ForegroundColor White
    $Config.OPENSEARCH_USERNAME = Read-UserInput -Prompt "OpenSearch username" -Default "admin"
    $Config.OPENSEARCH_PASSWORD = Read-UserInput -Prompt "OpenSearch password" -IsPassword
    
    Write-Success "Infrastructure credentials configured"
}

function Step-TokenGeneration {
    param([hashtable]$Config)
    
    Write-Step -Step "7/8" -Title "OLAV Token Generation"
    
    Write-Host ""
    Write-Host "Generating OLAV API tokens..." -ForegroundColor Cyan
    
    # Generate a random JWT secret
    $Config.JWT_SECRET_KEY = [System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    
    Write-Success "JWT secret key generated"
    Write-Host ""
    Write-Host "Note: After services start, run 'uv run olav register' to create client sessions" -ForegroundColor Yellow
}

function Step-ConfigConfirmation {
    param([hashtable]$Config)
    
    Write-Step -Step "8/8" -Title "Configuration Summary"
    
    Write-Host ""
    Write-Host "Configuration Summary:" -ForegroundColor White
    Write-Host "----------------------------------------"
    Write-Host "  Mode:           Production" -ForegroundColor Cyan
    Write-Host "  LLM Provider:   $($Config.LLM_PROVIDER)" -ForegroundColor Cyan
    Write-Host "  LLM Model:      $($Config.LLM_MODEL_NAME)" -ForegroundColor Cyan
    Write-Host "  Embedding:      $($Config.EMBEDDING_PROVIDER) / $($Config.EMBEDDING_MODEL)" -ForegroundColor Cyan
    Write-Host "  NetBox:         $(if ($Config.NETBOX_LOCAL) { 'Local (Docker)' } else { $Config.NETBOX_URL })" -ForegroundColor Cyan
    Write-Host "  OpenSearch:     Security Enabled" -ForegroundColor Cyan
    Write-Host "----------------------------------------"
    
    Write-Host ""
    $confirm = Read-UserInput -Prompt "Proceed with this configuration? [Y/n]" -Default "Y"
    
    if ($confirm -notmatch '^[Yy]') {
        Write-Host "Setup cancelled." -ForegroundColor Yellow
        exit 0
    }
}

function Generate-EnvFile-Production {
    param([hashtable]$Config)
    
    $envLines = @(
        "# ============================================"
        "# OLAV Configuration"
        "# Generated by Setup Wizard (Production Mode)"
        "# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "# ============================================"
        ""
        "# Deployment Mode"
        "OLAV_MODE=production"
        ""
        "# LLM Configuration"
        "LLM_PROVIDER=$($Config.LLM_PROVIDER)"
        "LLM_API_KEY=$($Config.LLM_API_KEY)"
        "LLM_MODEL_NAME=$($Config.LLM_MODEL_NAME)"
    )
    
    if ($Config.LLM_BASE_URL) {
        $envLines += "LLM_BASE_URL=$($Config.LLM_BASE_URL)"
    }
    
    $envLines += @(
        ""
        "# Embedding Configuration"
        "EMBEDDING_PROVIDER=$($Config.EMBEDDING_PROVIDER)"
        "EMBEDDING_MODEL=$($Config.EMBEDDING_MODEL)"
    )
    
    if ($Config.EMBEDDING_API_KEY) {
        $envLines += "EMBEDDING_API_KEY=$($Config.EMBEDDING_API_KEY)"
    }
    
    if ($Config.EMBEDDING_BASE_URL) {
        $envLines += "EMBEDDING_BASE_URL=$($Config.EMBEDDING_BASE_URL)"
    }
    
    $envLines += @(
        ""
        "# Device Credentials"
        "DEVICE_USERNAME=$($Config.DEVICE_USERNAME)"
        "DEVICE_PASSWORD=$($Config.DEVICE_PASSWORD)"
        "DEVICE_ENABLE_PASSWORD=$($Config.DEVICE_ENABLE_PASSWORD)"
        ""
        "# NetBox"
        "NETBOX_URL=$($Config.NETBOX_URL)"
        "NETBOX_TOKEN=$($Config.NETBOX_TOKEN)"
    )
    
    if ($Config.NETBOX_LOCAL) {
        $envLines += @(
            "NETBOX_SUPERUSER_NAME=$($Config.NETBOX_SUPERUSER_NAME)"
            "NETBOX_SUPERUSER_EMAIL=$($Config.NETBOX_SUPERUSER_EMAIL)"
            "NETBOX_SUPERUSER_PASSWORD=$($Config.NETBOX_SUPERUSER_PASSWORD)"
            "NETBOX_SECRET_KEY=production-secret-key-$(Get-Random)"
        )
    }
    
    $envLines += @(
        ""
        "# PostgreSQL"
        "POSTGRES_USER=$($Config.POSTGRES_USER)"
        "POSTGRES_PASSWORD=$($Config.POSTGRES_PASSWORD)"
        "POSTGRES_DB=olav"
        ""
        "# OpenSearch (Security Enabled)"
        "OPENSEARCH_SECURITY_DISABLED=false"
        "OPENSEARCH_USERNAME=$($Config.OPENSEARCH_USERNAME)"
        "OPENSEARCH_PASSWORD=$($Config.OPENSEARCH_PASSWORD)"
        ""
        "# JWT Configuration"
        "JWT_SECRET_KEY=$($Config.JWT_SECRET_KEY)"
        ""
        "# Port Configuration"
        "OPENSEARCH_PORT=$($Config.OPENSEARCH_PORT)"
        "POSTGRES_PORT=$($Config.POSTGRES_PORT)"
        "NETBOX_PORT=$($Config.NETBOX_PORT)"
    )
    
    return $envLines -join "`n"
}

function Show-Completion {
    param([hashtable]$Config)
    
    Write-Host ""
    Write-Host @"
========================================
        🎉 Setup Complete!
========================================
"@ -ForegroundColor Green
    
    Write-Host ""
    Write-Host "Access:" -ForegroundColor White
    Write-Host "  - OLAV CLI:    uv run olav" -ForegroundColor Cyan
    Write-Host "  - NetBox:      http://localhost:$($Config.NETBOX_PORT) (admin/admin)" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Host "Configuration saved to: .env" -ForegroundColor White
    
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Run 'uv run olav' to start chatting with OLAV"
    Write-Host "  2. Add devices to NetBox if you haven't imported from CSV"
    Write-Host ""
}

function Show-Completion-Production {
    param([hashtable]$Config)
    
    Write-Host ""
    Write-Host @"
========================================
    🎉 Production Setup Complete!
========================================
"@ -ForegroundColor Green
    
    Write-Host ""
    Write-Host "Access:" -ForegroundColor White
    Write-Host "  - OLAV CLI:    uv run olav" -ForegroundColor Cyan
    if ($Config.NETBOX_LOCAL) {
        Write-Host "  - NetBox:      http://localhost:$($Config.NETBOX_PORT) ($($Config.NETBOX_SUPERUSER_NAME)/***)" -ForegroundColor Cyan
    }
    else {
        Write-Host "  - NetBox:      $($Config.NETBOX_URL)" -ForegroundColor Cyan
    }
    Write-Host "  - OpenSearch:  http://localhost:$($Config.OPENSEARCH_PORT)" -ForegroundColor Cyan
    
    Write-Host ""
    Write-Host "Configuration saved to: .env" -ForegroundColor White
    
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Run 'uv run olav register' to create client session"
    Write-Host "  2. Run 'uv run olav' to start chatting with OLAV"
    Write-Host "  3. Review OpenSearch security settings if needed"
    Write-Host ""
}

# ============================================
# Main Entry Point
# ============================================

function Main {
    # Select mode if not specified
    if ([string]::IsNullOrEmpty($Mode)) {
        $Mode = Select-DeploymentMode
    }
    
    Write-Banner
    Write-Host "Starting $Mode mode setup..." -ForegroundColor Cyan
    
    # Configuration hashtable
    $Config = @{
        Mode = $Mode
    }
    
    if ($Mode -eq "QuickTest") {
        # Quick Test Mode: 7 steps (optimized order)
        # 1-4: Configuration
        Step-LLMConfiguration -Config $Config
        Step-EmbeddingConfiguration -Config $Config
        Step-DeviceCredentials -Config $Config
        Step-PortCheck -Config $Config
        # 5: Start NetBox first (needed for inventory)
        Step-StartNetBox -Config $Config
        # 6: Initialize NetBox with inventory.csv
        Step-NetBoxInventoryInit -Config $Config
        # 7: Start remaining services
        Step-StartRemainingServices -Config $Config
        # 8: Schema initialization
        Step-SchemaInit -Config $Config
        Show-Completion -Config $Config
    }
    else {
        # Production Mode: 8 steps
        # Step 1: NetBox configuration (existing vs new)
        Step-NetBoxConfiguration -Config $Config
        
        # Step 2: LLM configuration
        Write-Step -Step "2/8" -Title "LLM Configuration"
        Step-LLMConfiguration -Config $Config -SkipHeader
        
        # Step 3: Embedding configuration
        Write-Step -Step "3/8" -Title "Embedding Configuration"
        Step-EmbeddingConfiguration -Config $Config -SkipHeader
        
        # Step 4: Device credentials
        Write-Step -Step "4/8" -Title "Device Credentials"
        Step-DeviceCredentials -Config $Config -SkipHeader
        
        # Step 5: Infrastructure credentials
        Step-InfraCredentials -Config $Config
        
        # Step 6: Port check & start services
        Write-Step -Step "6/8" -Title "Port Check & Start Services"
        Step-PortCheck -Config $Config -SkipHeader
        Step-StartServices -Config $Config -SkipHeader
        
        # Step 7: Token generation
        Step-TokenGeneration -Config $Config
        
        # Step 8: Configuration confirmation
        Step-ConfigConfirmation -Config $Config
        
        # Schema initialization
        Step-SchemaInit -Config $Config -SkipHeader
        
        # Generate production .env file
        $envContent = Generate-EnvFile-Production -Config $Config
        Set-Content -Path ".env" -Value $envContent -Encoding UTF8
        Write-Success ".env file generated for production"
        
        Show-Completion-Production -Config $Config
    }
}

# Run
Main
