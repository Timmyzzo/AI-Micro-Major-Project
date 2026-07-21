<#
.SYNOPSIS
Start the local PowerInsight Streamlit app and open it in the default browser.
#>

[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$PreferredPort = 8501,

    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppPath = Join-Path $ProjectRoot "app\streamlit_app.py"
$CandidatePorts = @($PreferredPort) + @(8501..8510 | Where-Object { $_ -ne $PreferredPort })

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    $message = "Project virtual environment was not found: $PythonPath" + [Environment]::NewLine
    throw ($message + "Run: uv sync --extra dev --frozen")
}

if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) {
    throw "Streamlit entrypoint was not found: $AppPath"
}

function Test-PowerInsightHealth {
    param([int]$Port)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/_stcore/health" -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Trim() -eq "ok"
    }
    catch {
        return $false
    }
}

function Get-PortListener {
    param([int]$Port)

    return Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Open-PowerInsight {
    param([int]$Port)

    $url = "http://127.0.0.1:$Port"
    if (-not $NoBrowser) {
        Start-Process $url
    }
    Write-Host "PowerInsight is ready: $url" -ForegroundColor Green
}

foreach ($candidatePort in $CandidatePorts) {
    $listener = Get-PortListener -Port $candidatePort
    if ($null -eq $listener) {
        continue
    }

    $owner = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = if ($null -eq $owner) { "" } else { [string]$owner.CommandLine }
    $isCurrentProject = $commandLine.IndexOf($AppPath, [StringComparison]::OrdinalIgnoreCase) -ge 0

    if ($isCurrentProject -and (Test-PowerInsightHealth -Port $candidatePort)) {
        Open-PowerInsight -Port $candidatePort
        exit 0
    }
}

$port = $null
foreach ($candidatePort in $CandidatePorts) {
    if ($null -eq (Get-PortListener -Port $candidatePort)) {
        $port = $candidatePort
        break
    }
}

if ($null -eq $port) {
    throw "Ports 8501-8510 are busy. No existing process was stopped."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutPath = Join-Path $env:TEMP "powerinsight-$port-$stamp.out.log"
$stderrPath = Join-Path $env:TEMP "powerinsight-$port-$stamp.err.log"
$arguments = @(
    "-m",
    "streamlit",
    "run",
    $AppPath,
    "--server.port",
    [string]$port,
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false"
)

$process = Start-Process -FilePath $PythonPath -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru

for ($attempt = 0; $attempt -lt 50; $attempt += 1) {
    if (Test-PowerInsightHealth -Port $port) {
        Open-PowerInsight -Port $port
        exit 0
    }
    if ($process.HasExited) {
        break
    }
    Start-Sleep -Milliseconds 250
}

$errorDetail = if (Test-Path -LiteralPath $stderrPath) {
    (Get-Content -LiteralPath $stderrPath -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
}
else {
    "No error log was generated."
}

$message = "PowerInsight failed to start. Error log: $stderrPath" + [Environment]::NewLine
throw ($message + $errorDetail)
