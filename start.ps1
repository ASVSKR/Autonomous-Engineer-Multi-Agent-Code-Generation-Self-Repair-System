# ============================================================
#  Hackathon - Start All Services (portable)
#  Usage:  .\start.ps1
#          .\start.ps1 -JavaPort 8081 -PythonPort 5001
#
#  This script prefers the PORTABLE tools bundled in this folder
#  (java\, maven\, Python\, wheelhouse\, .m2-repo\) created by
#  setup-portable.ps1. If they are absent it falls back to whatever
#  Java / Maven / Python is on the system PATH.
# ============================================================
param(
    [int]$JavaPort   = 8080,
    [int]$PythonPort = 5000
)

$Root       = $PSScriptRoot
$JavaSvc    = Join-Path $Root "service\service"
$AgentSvc   = Join-Path $Root "agentService"
$AgentEnv   = Join-Path $AgentSvc ".env"
$Requirements = Join-Path $AgentSvc "requirements.txt"

# Bundled portable tool locations
$LocalJavaHome = Join-Path $Root "java"
$LocalJavaExe  = Join-Path $LocalJavaHome "bin\java.exe"
$LocalMavenBin = Join-Path $Root "maven\bin"
$LocalMavenCmd = Join-Path $LocalMavenBin "mvn.cmd"
$BundledPython = Join-Path $Root "Python\python.exe"
$Wheelhouse    = Join-Path $Root "wheelhouse"
$MavenRepo     = Join-Path $Root ".m2-repo"
$VenvDir       = Join-Path $AgentSvc ".venv"
$VenvPython    = Join-Path $VenvDir "Scripts\python.exe"

# ── helpers ─────────────────────────────────────────────────
function Write-Header($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

function Check-Port($port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conn
}

function Get-DotenvValue($filePath, $key) {
    if (-not (Test-Path $filePath)) { return $null }
    foreach ($line in Get-Content -Path $filePath -ErrorAction SilentlyContinue) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
        if ($trimmed.StartsWith("#")) { continue }
        if (-not $trimmed.StartsWith("$key=")) { continue }
        $value = $trimmed.Substring($key.Length + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        return $value
    }
    return $null
}

function Test-PythonExe($exe) {
    if (-not (Test-Path $exe)) { return $false }
    try { & $exe -c "import sys" 2>$null; return ($LASTEXITCODE -eq 0) }
    catch { return $false }
}

# ── pre-flight checks ────────────────────────────────────────
Write-Header "Pre-flight checks"

$groqFromEnvFile = Get-DotenvValue -filePath $AgentEnv -key "GROQ_API_KEY"
$effectiveGroqApiKey = $env:GROQ_API_KEY
if (-not $effectiveGroqApiKey -and $groqFromEnvFile) {
    $effectiveGroqApiKey = $groqFromEnvFile
    $env:GROQ_API_KEY = $groqFromEnvFile
}
if (-not $effectiveGroqApiKey) {
    Write-Host "[WARN] GROQ_API_KEY is not set. Agent LLM calls will fail." -ForegroundColor Yellow
    Write-Host "       Get a free key at: https://console.groq.com" -ForegroundColor Yellow
}

if (Check-Port $JavaPort)   { Write-Host "[WARN] Port $JavaPort already in use - Java service may already be running." -ForegroundColor Yellow }
if (Check-Port $PythonPort) { Write-Host "[WARN] Port $PythonPort already in use - Python service may already be running." -ForegroundColor Yellow }

# ── resolve portable toolchain ───────────────────────────────
Write-Header "Resolving toolchain"

# Java
if (Test-Path $LocalJavaExe) {
    $env:JAVA_HOME = $LocalJavaHome
    $env:PATH = (Join-Path $LocalJavaHome "bin") + ";" + $env:PATH
    Write-Host "  Java   : bundled  ($LocalJavaExe)" -ForegroundColor Green
} else {
    Write-Host "  Java   : system PATH (bundled java\ not found - run setup-portable.ps1)" -ForegroundColor Yellow
}

# Maven: prefer bundled; choose the command used to launch the Spring service
if (Test-Path $LocalMavenCmd) {
    $env:PATH = $LocalMavenBin + ";" + $env:PATH
    $serviceBuildCmd = "mvn.cmd"
    Write-Host "  Maven  : bundled  ($LocalMavenCmd)" -ForegroundColor Green
} elseif (Test-Path (Join-Path $JavaSvc "mvnw.cmd")) {
    $serviceBuildCmd = "mvnw.cmd"
    Write-Host "  Maven  : service mvnw wrapper (will download Maven on first run)" -ForegroundColor Yellow
} else {
    $serviceBuildCmd = "mvn.cmd"
    Write-Host "  Maven  : system PATH (bundled maven\ not found - run setup-portable.ps1)" -ForegroundColor Yellow
}

# Offline Maven repository (used by both the service and generated builds)
if (Test-Path $MavenRepo) {
    $env:MAVEN_ARGS = "-Dmaven.repo.local=$MavenRepo"
    Write-Host "  M2 repo: bundled  (.m2-repo)" -ForegroundColor Green
}

# ── Python virtual environment (.venv) ───────────────────────
Write-Header "Preparing Python environment (.venv)"

# A .venv copied from another machine hard-codes paths; recreate if invalid.
if ((Test-Path $VenvPython) -and -not (Test-PythonExe $VenvPython)) {
    Write-Host "  Existing .venv is invalid (copied/stale) - recreating" -ForegroundColor Yellow
    Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $VenvPython)) {
    # Pick the base interpreter to create the venv from
    $basePython = $null
    if (Test-PythonExe $BundledPython) { $basePython = $BundledPython; Write-Host "  Base   : bundled Python\python.exe" -ForegroundColor Green }
    else {
        $sysPy = (Get-Command python -ErrorAction SilentlyContinue)
        if ($sysPy) { $basePython = $sysPy.Source; Write-Host "  Base   : system python ($($sysPy.Source))" -ForegroundColor Yellow }
    }

    if (-not $basePython) {
        Write-Host "[ERROR] No Python found. Run setup-portable.ps1 or install Python." -ForegroundColor Red
        exit 1
    }

    Write-Host "  Creating .venv ..." -ForegroundColor Gray
    & $basePython -m venv $VenvDir
    if (-not (Test-Path $VenvPython)) { Write-Host "[ERROR] Failed to create .venv" -ForegroundColor Red; exit 1 }

    & $VenvPython -m pip install --upgrade pip --quiet
    if (Test-Path $Requirements) {
        if (Test-Path $Wheelhouse) {
            Write-Host "  Installing dependencies (offline wheelhouse) ..." -ForegroundColor Gray
            & $VenvPython -m pip install --no-index --find-links $Wheelhouse -r $Requirements
        } else {
            Write-Host "  Installing dependencies (online) ..." -ForegroundColor Gray
            & $VenvPython -m pip install -r $Requirements
        }
    }
    Write-Host "  .venv ready" -ForegroundColor Green
} else {
    Write-Host "  Reusing existing .venv" -ForegroundColor Green
}

# Tell the agent runtime which interpreter to use for any child Python it spawns
$env:AGENT_PYTHON_EXECUTABLE = $VenvPython

# ── Java Spring Boot service ─────────────────────────────────
Write-Header "Starting Java Spring Boot service on port $JavaPort"

$javaArgs = @{
    FilePath         = "cmd.exe"
    ArgumentList     = "/k", "cd /d `"$JavaSvc`" && $serviceBuildCmd spring-boot:run -Dserver.port=$JavaPort"
    WorkingDirectory = $JavaSvc
    PassThru         = $true
}
$javaProc = Start-Process @javaArgs
Write-Host "  Java service starting (PID: $($javaProc.Id)) - wait ~30s for Spring Boot startup" -ForegroundColor Green

# ── Python Flask / Agent service ─────────────────────────────
Write-Header "Starting Python Agent service on port $PythonPort"

$env:APP_PORT      = "$PythonPort"
$env:JIRA_BASE_URL = "http://localhost:$JavaPort"
# JIRA_STUB_ENABLED defaults to false: new tickets are created via the real
# Java Jira endpoint (POST /jira/create). Set $env:JIRA_STUB_ENABLED="true" to
# run the agent offline without the Java service.

$pythonArgs = @{
    FilePath         = "cmd.exe"
    ArgumentList     = "/k", "cd /d `"$AgentSvc`" && `"$VenvPython`" main.py"
    WorkingDirectory = $AgentSvc
    PassThru         = $true
}
$pyProc = Start-Process @pythonArgs
Write-Host "  Python service starting (PID: $($pyProc.Id))" -ForegroundColor Green

# ── summary ──────────────────────────────────────────────────
Write-Header "Services started"
Write-Host ""
Write-Host "  Java  Spring Boot  ->  http://localhost:$JavaPort"    -ForegroundColor White
Write-Host "  Python Flask       ->  http://localhost:$PythonPort"  -ForegroundColor White
Write-Host ""
Write-Host "  Useful endpoints:"
Write-Host "    GET  http://localhost:$PythonPort/health"
Write-Host "    GET  http://localhost:$PythonPort/runtime"
Write-Host "    GET  http://localhost:$PythonPort/config/active"
Write-Host "    POST http://localhost:$PythonPort/workflow/run"
Write-Host ""
Write-Host "  To stop: close the two terminal windows that opened, or:" -ForegroundColor DarkGray
Write-Host "    Stop-Process -Id $($javaProc.Id)   # Java" -ForegroundColor DarkGray
Write-Host "    Stop-Process -Id $($pyProc.Id)   # Python" -ForegroundColor DarkGray
