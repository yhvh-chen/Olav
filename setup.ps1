#Requires -Version 5.1
<#!
OLAV minimal setup (env-driven)

Goal:
- User manually copies .env.example -> .env and edits values (ports, secrets, endpoints)
- This script reads .env, selects mode (QuickTest default), and starts Docker services.

Usage:
  .\setup.ps1                 # Auto (defaults to QuickTest unless .env sets OLAV_MODE=production)
  .\setup.ps1 -Mode QuickTest
  .\setup.ps1 -Mode Production

Notes:
- QuickTest forces AUTH_DISABLED=true and OPENSEARCH_SECURITY_DISABLED=true at runtime.
- Production forces AUTH_DISABLED=false and OPENSEARCH_SECURITY_DISABLED=false and requires OLAV_API_TOKEN.
#>

[CmdletBinding()]
param(
    [ValidateSet('','QuickTest','Production')]
    [string]$Mode = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:UseComposePlugin = $false

function Write-Info([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
function Write-Success([string]$Message) { Write-Host "✓ $Message" -ForegroundColor Green }
function Write-WarningMsg([string]$Message) { Write-Host "⚠ $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "✗ $Message" -ForegroundColor Red }

function New-StrongHexSecret {
    param(
        [int]$Bytes = 32
    )

    $buf = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    return ($buf | ForEach-Object { $_.ToString('x2') }) -join ''
}

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content -Path $Path
    }

    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*=.*$"
    $replaced = $false

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $replaced = $true
            break
        }
    }

    if (-not $replaced) {
        $lines += "$Key=$Value"
    }

    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

function Read-DotEnvFile {
    param([string]$Path)

    $result = @{}
    if (-not (Test-Path $Path)) {
        return $result
    }

    foreach ($line in Get-Content -Path $Path) {
        if (-not $line) { continue }
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith('#')) { continue }
        $eq = $trimmed.IndexOf('=')
        if ($eq -lt 1) { continue }
        $key = $trimmed.Substring(0, $eq).Trim()
        $val = $trimmed.Substring($eq + 1).Trim()
        $result[$key] = $val
    }

    return $result
}

function Assert-CommandsPresent {
    $missing = @()

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { $missing += 'docker' }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { $missing += 'uv' }

    $hasComposeShim = (Get-Command docker-compose -ErrorAction SilentlyContinue) -ne $null
    try {
        & docker compose version 2>$null | Out-Null
        $script:UseComposePlugin = $true
    }
    catch {
        $script:UseComposePlugin = $false
    }

    if (-not $script:UseComposePlugin -and -not $hasComposeShim) {
        $missing += 'docker compose (plugin) or docker-compose (shim)'
    }

    if ($missing.Count -gt 0) {
        Write-Fail "Missing required command(s): $($missing -join ', ')"
        throw "Missing commands"
    }
}

function Assert-EnvExists {
    param([string]$EnvPath, [string]$ExamplePath)

    if (Test-Path $EnvPath) { return }

    Write-Fail ".env not found. Please create it first."
    Write-Host ""
    Write-Host "From repo root:" -ForegroundColor White
    Write-Host "  Copy-Item .env.example .env" -ForegroundColor Gray
    Write-Host "  notepad .env" -ForegroundColor Gray
    Write-Host ""
    if (Test-Path $ExamplePath) {
        Write-Host "Template: $ExamplePath" -ForegroundColor Gray
    }
    throw ".env missing"
}

function Get-EnvValue {
    param(
        [hashtable]$EnvMap,
        [string]$Key,
        [string]$Default = ''
    )
    if ($EnvMap.ContainsKey($Key) -and -not [string]::IsNullOrWhiteSpace([string]$EnvMap[$Key])) {
        return [string]$EnvMap[$Key]
    }
    return $Default
}

function Assert-RequiredVars {
    param(
        [hashtable]$EnvMap,
        [string[]]$RequiredKeys,
        [string]$Context
    )

    $missing = @()
    foreach ($k in $RequiredKeys) {
        if (-not $EnvMap.ContainsKey($k) -or [string]::IsNullOrWhiteSpace([string]$EnvMap[$k])) {
            $missing += $k
        }
    }

    if ($missing.Count -gt 0) {
        Write-Fail "Missing required .env keys for ${Context}: $($missing -join ', ')"
        throw "Missing .env keys"
    }
}

function Invoke-Compose {
    param(
        [string[]]$ComposeArgs
    )

    if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
        throw "Invoke-Compose called with empty arguments"
    }

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($script:UseComposePlugin) {
            & docker compose @ComposeArgs
            return
        }

        if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
            & docker-compose @ComposeArgs
            return
        }

        # Final fallback (should not happen if Assert-CommandsPresent ran)
        & docker compose @ComposeArgs
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
}

function Invoke-ComposeWithDiagnostics {
    param(
        [string]$ProjectRoot,
        [string[]]$ComposeArgs,
        [switch]$TreatFailureAsWarning
    )

    Push-Location $ProjectRoot
    try {
        if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
            throw "Invoke-ComposeWithDiagnostics called with empty arguments"
        }
        $output = Invoke-Compose -ComposeArgs $ComposeArgs 2>&1
        if ($LASTEXITCODE -ne 0) {
            if ($TreatFailureAsWarning) {
                Write-WarningMsg "Docker compose returned exit $LASTEXITCODE (continuing): docker compose $($ComposeArgs -join ' ')"
                Write-Host $output
            }
            else {
                Write-Fail "Docker compose failed (exit $LASTEXITCODE): docker compose $($ComposeArgs -join ' ')"
                Write-Host $output
                throw "docker compose failed"
            }
        }

        return $output
    }
    finally {
        Pop-Location
    }
}

function Invoke-ComposeStreamingWithDiagnostics {
    param(
        [string]$ProjectRoot,
        [string[]]$ComposeArgs,
        [switch]$TreatFailureAsWarning
    )

    Push-Location $ProjectRoot
    try {
        if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
            throw "Invoke-ComposeStreamingWithDiagnostics called with empty arguments"
        }
        Invoke-Compose -ComposeArgs $ComposeArgs
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            if ($TreatFailureAsWarning) {
                Write-WarningMsg "Docker compose returned exit $exitCode (continuing): docker compose $($ComposeArgs -join ' ')"
            }
            else {
                Write-Fail "Docker compose failed (exit $exitCode): docker compose $($ComposeArgs -join ' ')"
                throw "docker compose failed"
            }
        }
    }
    finally {
        Pop-Location
    }
}

function Format-ProcessArg {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Arg
    )

    if ($null -eq $Arg) {
        return '""'
    }

    if ($Arg -match '[\s"]') {
        $escaped = $Arg -replace '"', '\\"'
        return '"' + $escaped + '"'
    }

    return $Arg
}

function Invoke-UvWithDiagnostics {
    param(
        [string]$ProjectRoot,
        [string[]]$UvArgs,
        [switch]$TreatFailureAsWarning
    )

    if (-not $UvArgs -or $UvArgs.Count -eq 0) {
        throw "Invoke-UvWithDiagnostics called with empty arguments"
    }

    $uvCmd = Get-Command uv -ErrorAction Stop
    $uvExe = $uvCmd.Source

    $stdoutPath = Join-Path $env:TEMP ("olav-uv-stdout-{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $stderrPath = Join-Path $env:TEMP ("olav-uv-stderr-{0}.log" -f ([guid]::NewGuid().ToString('N')))

    $argLine = ($UvArgs | ForEach-Object { Format-ProcessArg -Arg $_ }) -join ' '

    Push-Location $ProjectRoot
    try {
        $proc = Start-Process -FilePath $uvExe -ArgumentList $argLine -NoNewWindow -PassThru -Wait -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

        $stdout = if (Test-Path $stdoutPath) { Get-Content -Raw -Path $stdoutPath } else { '' }
        $stderr = if (Test-Path $stderrPath) { Get-Content -Raw -Path $stderrPath } else { '' }

        if (-not [string]::IsNullOrWhiteSpace($stdout)) { Write-Host $stdout }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) { Write-Host $stderr }

        if ($proc.ExitCode -ne 0) {
            if ($TreatFailureAsWarning) {
                Write-WarningMsg "uv exited with code $($proc.ExitCode) (continuing): uv $($UvArgs -join ' ')"
            }
            else {
                Write-Fail "uv failed (exit $($proc.ExitCode)): uv $($UvArgs -join ' ')"
                throw "uv failed"
            }
        }

        return @{
            ExitCode = $proc.ExitCode
            Stdout = $stdout
            Stderr = $stderr
        }
    }
    finally {
        Remove-Item $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
        Pop-Location
    }
}

function Wait-ForOlavServer {
    param(
        [string]$ServerPort,
        [int]$TimeoutSeconds = 120
    )

    $serverUrl = "http://127.0.0.1:$ServerPort"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null

    Write-Info "Waiting for OLAV API to be reachable at $serverUrl/health (timeout: ${TimeoutSeconds}s)..."

    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "$serverUrl/health" -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                Write-Success "OLAV API is reachable"
                return $true
            }
            $lastError = "HTTP $($resp.StatusCode)"
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }

    Write-Fail "OLAV API not reachable after ${TimeoutSeconds}s: $lastError"
    return $false
}

function ConvertTo-Bool {
    param(
        [string]$Value,
        [bool]$Default = $false
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $Default }
    $v = $Value.Trim().ToLowerInvariant()
    if ($v -in @('1','true','yes','y','on','enable','enabled')) { return $true }
    if ($v -in @('0','false','no','n','off','disable','disabled')) { return $false }
    return $Default
}

function Wait-ForContainerHealthy {
    param(
        [string]$ContainerName,
        [int]$TimeoutSeconds = 240
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    Write-Info "Waiting for container to be healthy: $ContainerName (timeout: ${TimeoutSeconds}s)..."

    while ((Get-Date) -lt $deadline) {
        try {
            $status = (& docker inspect -f '{{.State.Health.Status}}' $ContainerName 2>$null)
            if ($LASTEXITCODE -eq 0 -and $status -and $status.Trim() -eq 'healthy') {
                Write-Success "$ContainerName is healthy"
                return $true
            }
        }
        catch {
            # ignore and retry
        }
        Start-Sleep -Seconds 3
    }

    Write-Fail "$ContainerName not healthy after ${TimeoutSeconds}s"
    return $false
}

function Invoke-NetBoxInit {
    param(
        [string]$ProjectRoot,
        [string]$NetBoxPort,
        [string]$InventoryCsvPath,
        [string]$NetBoxToken,
        [string]$DeviceUsername,
        [string]$DevicePassword,
        [switch]$Force
    )

    if ([string]::IsNullOrWhiteSpace($InventoryCsvPath)) {
        Write-WarningMsg "INVENTORY_CSV_PATH not set; skipping NetBox inventory init"
        return
    }

    $csvFullPath = $InventoryCsvPath
    if (-not [System.IO.Path]::IsPathRooted($csvFullPath)) {
        $csvFullPath = Join-Path $ProjectRoot $InventoryCsvPath
    }
    if (-not (Test-Path $csvFullPath)) {
        Write-WarningMsg "Inventory CSV not found: $csvFullPath (skipping NetBox inventory init)"
        return
    }

    $netboxHostUrl = "http://127.0.0.1:$NetBoxPort"
    Write-Info "Initializing NetBox inventory from: $csvFullPath"

    Push-Location $ProjectRoot
    try {
        $oldNetboxUrl = $env:NETBOX_URL
        $oldNetboxToken = $env:NETBOX_TOKEN
        $oldDeviceUsername = $env:DEVICE_USERNAME
        $oldDevicePassword = $env:DEVICE_PASSWORD
        $env:NETBOX_URL = $netboxHostUrl
        # Ensure NETBOX_TOKEN is present for check_netbox.py/scripts/netbox_ingest.py.
        if (-not [string]::IsNullOrWhiteSpace($NetBoxToken)) {
            $env:NETBOX_TOKEN = $NetBoxToken
        }

        if (-not [string]::IsNullOrWhiteSpace($DeviceUsername)) {
            $env:DEVICE_USERNAME = $DeviceUsername
        }
        if (-not [string]::IsNullOrWhiteSpace($DevicePassword)) {
            $env:DEVICE_PASSWORD = $DevicePassword
        }

        $args = @('run', 'olav', 'init', 'netbox', '--csv', $csvFullPath)
        if ($Force) { $args += '--force' }

        Invoke-UvWithDiagnostics -ProjectRoot $ProjectRoot -UvArgs $args -TreatFailureAsWarning | Out-Null
        Write-Success "NetBox inventory init completed"
    }
    finally {
        if ($null -ne $oldNetboxUrl) { $env:NETBOX_URL = $oldNetboxUrl } else { Remove-Item Env:NETBOX_URL -ErrorAction SilentlyContinue }
        if ($null -ne $oldNetboxToken) { $env:NETBOX_TOKEN = $oldNetboxToken } else { Remove-Item Env:NETBOX_TOKEN -ErrorAction SilentlyContinue }
        if ($null -ne $oldDeviceUsername) { $env:DEVICE_USERNAME = $oldDeviceUsername } else { Remove-Item Env:DEVICE_USERNAME -ErrorAction SilentlyContinue }
        if ($null -ne $oldDevicePassword) { $env:DEVICE_PASSWORD = $oldDevicePassword } else { Remove-Item Env:DEVICE_PASSWORD -ErrorAction SilentlyContinue }
        Pop-Location
    }
}

function Invoke-DockerComposeUp {
    param(
        [string]$ProjectRoot,
        [string]$Mode
    )

    $env:OLAV_MODE = if ($Mode -eq 'Production') { 'production' } else { 'quicktest' }

    Write-Info "Starting Docker services (compose --profile netbox up -d)..."

    # NOTE: docker compose may return non-zero if a dependent service is unhealthy.
    # We treat that as a warning and proceed to verify the OLAV API itself.
    Invoke-ComposeWithDiagnostics -ProjectRoot $ProjectRoot -ComposeArgs @('--profile', 'netbox', 'up', '-d') -TreatFailureAsWarning | Out-Null
}

function Invoke-DockerComposePrepare {
    param(
        [string]$ProjectRoot,
        [switch]$UseNetBoxProfile
    )

    $profileArgs = @()
    if ($UseNetBoxProfile) {
        $profileArgs = @('--profile', 'netbox')
    }

    Write-Info "Preparing Docker images (pull + build in parallel)..."

    # Start `docker compose pull` in background (captured to a log file), while `docker compose build` streams live.
    $pullOut = Join-Path $env:TEMP 'olav-compose-pull.out.log'
    $pullErr = Join-Path $env:TEMP 'olav-compose-pull.err.log'
    Remove-Item $pullOut, $pullErr -ErrorAction SilentlyContinue

    $composeExe = if ($script:UseComposePlugin) { 'docker' } else { 'docker-compose' }
    $composePrefix = if ($script:UseComposePlugin) { @('compose') } else { @() }

    # Prefer plain progress so output is readable in logs.
    $pullComposeArgs = @()
    $pullComposeArgs += $composePrefix
    $pullComposeArgs += $profileArgs
    $pullComposeArgs += @('--progress', 'plain', 'pull')

    $buildArgs = @()
    $buildArgs += $profileArgs
    $buildArgs += @('--progress', 'plain', 'build')

    Write-Info "Starting pull (background)..."
    Push-Location $ProjectRoot
    try {
        $pullArgLine = ($pullComposeArgs -join ' ')
        Write-Host ("Running (background): {0} {1}" -f $composeExe, $pullArgLine) -ForegroundColor DarkGray
        $pullProc = Start-Process -FilePath $composeExe -ArgumentList $pullArgLine -NoNewWindow -PassThru -RedirectStandardOutput $pullOut -RedirectStandardError $pullErr
    }
    finally {
        Pop-Location
    }

    Write-Info "Starting build (foreground)..."
    Invoke-ComposeStreamingWithDiagnostics -ProjectRoot $ProjectRoot -ComposeArgs $buildArgs
    Write-Success "Docker image build complete"

    Write-Info "Waiting for pull to complete..."
    try {
        Wait-Process -Id $pullProc.Id -ErrorAction Stop
    }
    catch {
        # If the process exits very quickly, it may no longer be found by PID.
        # In that case, we still attempt to read ExitCode from the process object.
    }
    try { $pullProc.Refresh() } catch { }

    Write-Host "---- docker compose pull (stdout) ----" -ForegroundColor DarkGray
    if (Test-Path $pullOut) { Get-Content -Path $pullOut | Write-Host }
    Write-Host "---- docker compose pull (stderr) ----" -ForegroundColor DarkGray
    if (Test-Path $pullErr) { Get-Content -Path $pullErr | Write-Host }

    $pullExitCode = $null
    try { $pullExitCode = $pullProc.ExitCode } catch { }
    if ($null -eq $pullExitCode) {
        Write-WarningMsg "Docker image pull exit code unavailable (continuing)"
    }
    elseif ($pullExitCode -ne 0) {
        Write-WarningMsg "Docker image pull exited with code $pullExitCode (continuing)"
    }
    else {
        Write-Success "Docker image pull complete"
    }
}

function Invoke-OlavStatus {
    param(
        [string]$ProjectRoot,
        [string]$ServerPort,
        [switch]$UseAuth,
        [string]$Token
    )

    $serverUrl = "http://127.0.0.1:$ServerPort"
    Write-Info "Running status check: uv run olav status --server $serverUrl"

    Push-Location $ProjectRoot
    try {
        $oldToken = $env:OLAV_API_TOKEN

        if ($UseAuth) {
            $env:OLAV_API_TOKEN = $Token
        }
        else {
            Remove-Item Env:OLAV_API_TOKEN -ErrorAction SilentlyContinue
        }

        $res = Invoke-UvWithDiagnostics -ProjectRoot $ProjectRoot -UvArgs @('run', 'olav', 'status', '--server', $serverUrl) -TreatFailureAsWarning
        if ($res.ExitCode -eq 0) {
            Write-Success "Status OK"
        }
        else {
            Write-WarningMsg "Status returned exit $($res.ExitCode)"
        }
    }
    finally {
        if ($null -ne $oldToken) { $env:OLAV_API_TOKEN = $oldToken } else { Remove-Item Env:OLAV_API_TOKEN -ErrorAction SilentlyContinue }
        Pop-Location
    }
}

function Resolve-Mode {
    param(
        [string]$ModeArg,
        [hashtable]$EnvMap
    )

    if (-not [string]::IsNullOrWhiteSpace($ModeArg)) {
        return $ModeArg
    }

    $raw = (Get-EnvValue -EnvMap $EnvMap -Key 'OLAV_MODE' -Default 'quicktest').Trim().ToLowerInvariant()
    if ($raw -eq 'production' -or $raw -eq 'prod') {
        return 'Production'
    }

    return 'QuickTest'
}

function Main {
    $projectRoot = $PSScriptRoot
    $envPath = Join-Path $projectRoot '.env'
    $envExample = Join-Path $projectRoot '.env.example'

    Assert-CommandsPresent
    Assert-EnvExists -EnvPath $envPath -ExamplePath $envExample

    $envMap = Read-DotEnvFile -Path $envPath
    $resolvedMode = Resolve-Mode -ModeArg $Mode -EnvMap $envMap

    Write-Info "OLAV setup (mode: $resolvedMode)"

    # Apply mode defaults at runtime (shell env overrides .env for docker-compose)
    if ($resolvedMode -eq 'QuickTest') {
        $env:AUTH_DISABLED = 'true'
        $env:OPENSEARCH_SECURITY_DISABLED = 'true'
        $env:OLAV_MODE = 'quicktest'
        Remove-Item Env:OLAV_API_TOKEN -ErrorAction SilentlyContinue
    }
    else {
        $env:AUTH_DISABLED = 'false'
        $env:OPENSEARCH_SECURITY_DISABLED = 'false'
        $env:OLAV_MODE = 'production'
    }

    # NetBox requires SECRET_KEY >= 50 characters.
    $rawNetboxSecret = Get-EnvValue -EnvMap $envMap -Key 'NETBOX_SECRET_KEY' -Default ''
    $generatedNetboxSecret = $false
    if ([string]::IsNullOrWhiteSpace($rawNetboxSecret) -or $rawNetboxSecret.Length -lt 50) {
        if ($resolvedMode -eq 'Production') {
            Write-Fail "NETBOX_SECRET_KEY must be at least 50 characters for Production mode."
            Write-Host "Fix .env (NETBOX_SECRET_KEY) then re-run setup." -ForegroundColor Gray
            throw "Invalid NETBOX_SECRET_KEY"
        }

        $newSecret = New-StrongHexSecret -Bytes 32  # 64 hex chars
        # Persist to .env so future runs are stable (docker compose always reads .env)
        Set-DotEnvValue -Path $envPath -Key 'NETBOX_SECRET_KEY' -Value $newSecret
        $env:NETBOX_SECRET_KEY = $newSecret
        $generatedNetboxSecret = $true

        if ([string]::IsNullOrWhiteSpace($rawNetboxSecret)) {
            Write-WarningMsg "NETBOX_SECRET_KEY missing; generated a temporary key for QuickTest."
        }
        else {
            Write-WarningMsg "NETBOX_SECRET_KEY too short; generated a temporary key for QuickTest."
        }
        Write-Host "Updated .env: NETBOX_SECRET_KEY set to a generated value (>= 50 chars)." -ForegroundColor Gray
    }

    # Validate minimal keys used by Docker compose / server
    $portKeys = @(
        'OLAV_SERVER_PORT',
        'OLAV_APP_PORT',
        'NETBOX_PORT',
        'POSTGRES_PORT',
        'OPENSEARCH_PORT',
        'OPENSEARCH_METRICS_PORT',
        'SUZIEQ_GUI_PORT',
        'FLUENT_SYSLOG_PORT',
        'FLUENT_HTTP_PORT'
    )
    Assert-RequiredVars -EnvMap $envMap -RequiredKeys $portKeys -Context 'Docker port mapping'

    if ($resolvedMode -eq 'Production') {
        Assert-RequiredVars -EnvMap $envMap -RequiredKeys @('OLAV_API_TOKEN') -Context 'Production auth'
    }

    $serverPort = Get-EnvValue -EnvMap $envMap -Key 'OLAV_SERVER_PORT' -Default '18001'
    $masterToken = Get-EnvValue -EnvMap $envMap -Key 'OLAV_API_TOKEN'

    $netboxEnabled = ConvertTo-Bool -Value (Get-EnvValue -EnvMap $envMap -Key 'NETBOX_ENABLED' -Default 'true') -Default $true
    $netboxAutoInit = ConvertTo-Bool -Value (Get-EnvValue -EnvMap $envMap -Key 'NETBOX_AUTO_INIT' -Default 'true') -Default $true
    $netboxAutoInitForce = ConvertTo-Bool -Value (Get-EnvValue -EnvMap $envMap -Key 'NETBOX_AUTO_INIT_FORCE' -Default 'false') -Default $false
    $inventoryCsvPath = Get-EnvValue -EnvMap $envMap -Key 'INVENTORY_CSV_PATH' -Default 'config/inventory.csv'
    $netboxPort = Get-EnvValue -EnvMap $envMap -Key 'NETBOX_PORT' -Default '18080'
    $netboxToken = Get-EnvValue -EnvMap $envMap -Key 'NETBOX_TOKEN' -Default ''
    $deviceUsername = Get-EnvValue -EnvMap $envMap -Key 'DEVICE_USERNAME' -Default ''
    $devicePassword = Get-EnvValue -EnvMap $envMap -Key 'DEVICE_PASSWORD' -Default ''

    # Pull/build images first, then start NetBox, init it, and finally bring up the rest.
    Invoke-DockerComposePrepare -ProjectRoot $projectRoot -UseNetBoxProfile:($netboxEnabled)

    if ($netboxEnabled) {
        Write-Info "NetBox enabled: starting NetBox first..."
        # Start ONLY NetBox dependencies first to ensure NetBox is healthy before other services.
        Invoke-ComposeWithDiagnostics -ProjectRoot $projectRoot -ComposeArgs @('--profile', 'netbox', 'up', '-d', 'netbox-postgres', 'netbox-redis', 'netbox-redis-cache', 'netbox') | Out-Null

        $nbOk = Wait-ForContainerHealthy -ContainerName 'olav-netbox' -TimeoutSeconds 300
        if (-not $nbOk) {
            Write-Host "";
            Write-Info "Recent netbox logs:";
            Invoke-ComposeWithDiagnostics -ProjectRoot $projectRoot -ComposeArgs @('--profile', 'netbox', 'logs', '--tail', '200', 'netbox') -TreatFailureAsWarning | Out-Null
            throw "NetBox not healthy"
        }

        if ($netboxAutoInit) {
            # Initialize NetBox inventory (creates tag if SUZIEQ_AUTO_TAG_ALL=true, and tags imported devices)
            Invoke-NetBoxInit -ProjectRoot $projectRoot -NetBoxPort $netboxPort -InventoryCsvPath $inventoryCsvPath -NetBoxToken $netboxToken -DeviceUsername $deviceUsername -DevicePassword $devicePassword -Force:$netboxAutoInitForce
        }
        else {
            Write-Info "NETBOX_AUTO_INIT=false: skipping NetBox inventory init"
        }
    }

    if ($netboxEnabled) {
        Invoke-DockerComposeUp -ProjectRoot $projectRoot -Mode $resolvedMode
    }
    else {
        $env:OLAV_MODE = if ($resolvedMode -eq 'Production') { 'production' } else { 'quicktest' }
        Write-Info "NetBox disabled: starting Docker services (compose up -d)..."
        Invoke-ComposeWithDiagnostics -ProjectRoot $projectRoot -ComposeArgs @('up', '-d') -TreatFailureAsWarning | Out-Null
    }
    Write-Success "Docker services started"

    if ($generatedNetboxSecret) {
        Write-Info "Recreating NetBox to apply generated NETBOX_SECRET_KEY..."
        Invoke-ComposeWithDiagnostics -ProjectRoot $projectRoot -ComposeArgs @('--profile', 'netbox', 'up', '-d', '--force-recreate', 'netbox') -TreatFailureAsWarning | Out-Null
    }

    $ok = Wait-ForOlavServer -ServerPort $serverPort -TimeoutSeconds 180
    if (-not $ok) {
        Write-Host "";
        Write-Info "docker compose ps:";
        Invoke-ComposeWithDiagnostics -ProjectRoot $projectRoot -ComposeArgs @('--profile', 'netbox', 'ps', '--all') -TreatFailureAsWarning | Out-Null
        Write-Host "";
        Write-Info "Recent olav-server logs:";
        Invoke-ComposeWithDiagnostics -ProjectRoot $projectRoot -ComposeArgs @('--profile', 'netbox', 'logs', '--tail', '200', 'olav-server') -TreatFailureAsWarning | Out-Null
        throw "OLAV server not reachable"
    }

    if ($resolvedMode -eq 'Production') {
        Invoke-OlavStatus -ProjectRoot $projectRoot -ServerPort $serverPort -UseAuth -Token $masterToken
    }
    else {
        Invoke-OlavStatus -ProjectRoot $projectRoot -ServerPort $serverPort
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "              Setup Complete" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""

    if ($resolvedMode -eq 'QuickTest') {
        Write-Host "Quick start (QuickTest):" -ForegroundColor Yellow
        Write-Host "  uv run olav" -ForegroundColor Gray
        Write-Host "  # (auth is disabled in QuickTest)" -ForegroundColor Gray
    }
    else {
        Write-Host "Next steps (Production):" -ForegroundColor Yellow
        Write-Host "  # Register a client (saves token to ~/.olav/credentials and server URL to ~/.olav/config.toml)" -ForegroundColor Gray
        Write-Host "  `$env:OLAV_API_TOKEN = '<master-token-from-.env>'" -ForegroundColor Gray
        Write-Host "  uv run olav register --name 'my-laptop' --server http://127.0.0.1:$serverPort" -ForegroundColor Gray
        Write-Host "  uv run olav" -ForegroundColor Gray
    }
}

Main
