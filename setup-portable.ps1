# ============================================================
#  Hackathon - Build a fully portable, shareable bundle
#  Run this ONCE on a machine WITH internet access. It downloads
#  Windows-native JDK + Maven + Python into this folder and prepares
#  an offline Python wheelhouse and a warmed Maven repository so the
#  recipient needs nothing pre-installed and (ideally) no internet.
#
#  Usage:
#    .\setup-portable.ps1                # download anything missing
#    .\setup-portable.ps1 -Force         # re-download/replace everything
#    .\setup-portable.ps1 -SkipMavenRepo # skip the (slow) repo warm-up
#
#  After it finishes, zip this whole folder and share it. The recipient
#  just unzips and runs:  .\start.ps1
# ============================================================
param(
    [switch]$Force,
    [switch]$SkipJava,
    [switch]$SkipMaven,
    [switch]$SkipPython,
    [switch]$SkipWheelhouse,
    [switch]$SkipMavenRepo,
    [string]$JdkVersion    = "21",
    [string]$MavenVersion  = "3.9.9",
    [string]$PythonVersion = "3.11.9"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root      = $PSScriptRoot
$JavaDir   = Join-Path $Root "java"
$MavenDir  = Join-Path $Root "maven"
$PythonDir = Join-Path $Root "Python"
$Wheelhouse = Join-Path $Root "wheelhouse"
$MavenRepo  = Join-Path $Root ".m2-repo"
$TempDir    = Join-Path $Root ".portable-tmp"
$AgentSvc   = Join-Path $Root "agentService"
$JavaSvc    = Join-Path $Root "service\service"
$Requirements = Join-Path $AgentSvc "requirements.txt"

function Write-Header($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)     { Write-Host "    [OK]  $msg" -ForegroundColor Green }
function Write-Info($msg)   { Write-Host "    $msg" -ForegroundColor Gray }
function Write-Warn2($msg)  { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }

function Reset-Temp {
    if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
}

function Download-File($url, $dest) {
    Write-Info "downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
}

# Replace $target with the single top-level folder produced by extracting $zip
function Expand-And-Flatten($zip, $target) {
    $extractTo = Join-Path $TempDir ("x_" + [System.IO.Path]::GetRandomFileName())
    Expand-Archive -Path $zip -DestinationPath $extractTo -Force
    $entries = Get-ChildItem $extractTo
    $source = if ($entries.Count -eq 1 -and $entries[0].PSIsContainer) { $entries[0].FullName } else { $extractTo }
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Move-Item -Path $source -Destination $target -Force
}

Reset-Temp
Write-Host "Portable bundle root: $Root" -ForegroundColor White

# ── 1. JDK (Windows x64) ─────────────────────────────────────
if (-not $SkipJava) {
    Write-Header "JDK (Temurin $JdkVersion, Windows x64)"
    $javaOk = Test-Path (Join-Path $JavaDir "bin\java.exe")
    if ($javaOk -and -not $Force) {
        Write-Ok "java\bin\java.exe already present (use -Force to replace)"
    } else {
        $jdkUrl = "https://api.adoptium.net/v3/binary/latest/$JdkVersion/ga/windows/x64/jdk/hotspot/normal/eclipse?project=jdk"
        $jdkZip = Join-Path $TempDir "jdk.zip"
        Download-File $jdkUrl $jdkZip
        Expand-And-Flatten $jdkZip $JavaDir
        if (Test-Path (Join-Path $JavaDir "bin\java.exe")) { Write-Ok "JDK -> java\" }
        else { throw "JDK extraction failed: java\bin\java.exe not found" }
    }
}

# ── 2. Apache Maven ──────────────────────────────────────────
if (-not $SkipMaven) {
    Write-Header "Apache Maven $MavenVersion"
    $mvnOk = Test-Path (Join-Path $MavenDir "bin\mvn.cmd")
    if ($mvnOk -and -not $Force) {
        Write-Ok "maven\bin\mvn.cmd already present (use -Force to replace)"
    } else {
        $mvnUrl = "https://archive.apache.org/dist/maven/maven-3/$MavenVersion/binaries/apache-maven-$MavenVersion-bin.zip"
        $mvnZip = Join-Path $TempDir "maven.zip"
        Download-File $mvnUrl $mvnZip
        Expand-And-Flatten $mvnZip $MavenDir
        if (Test-Path (Join-Path $MavenDir "bin\mvn.cmd")) { Write-Ok "Maven -> maven\" }
        else { throw "Maven extraction failed: maven\bin\mvn.cmd not found" }
    }
}

# ── 3. Python (relocatable, via NuGet python package) ────────
if (-not $SkipPython) {
    Write-Header "Python $PythonVersion (Windows, relocatable)"
    $pyOk = Test-Path (Join-Path $PythonDir "python.exe")
    if ($pyOk -and -not $Force) {
        Write-Ok "Python\python.exe already present (use -Force to replace)"
    } else {
        # The NuGet "python" package ships a full, relocatable CPython under tools/.
        $pyUrl = "https://www.nuget.org/api/v2/package/python/$PythonVersion"
        $pyZip = Join-Path $TempDir "python.nupkg.zip"
        Download-File $pyUrl $pyZip
        $pyExtract = Join-Path $TempDir "python_extract"
        Expand-Archive -Path $pyZip -DestinationPath $pyExtract -Force
        $toolsDir = Join-Path $pyExtract "tools"
        if (-not (Test-Path (Join-Path $toolsDir "python.exe"))) { throw "Python package missing tools\python.exe" }
        if (Test-Path $PythonDir) { Remove-Item $PythonDir -Recurse -Force }
        Move-Item -Path $toolsDir -Destination $PythonDir -Force
        Write-Ok "Python -> Python\"
    }

    $pythonExe = Join-Path $PythonDir "python.exe"
    Write-Info "ensuring pip"
    & $pythonExe -m ensurepip --default-pip | Out-Null
    & $pythonExe -m pip install --upgrade pip --quiet
    Write-Ok "pip ready ($(& $pythonExe -m pip --version))"
}

# ── 4. Offline wheelhouse for Python dependencies ────────────
if (-not $SkipWheelhouse) {
    Write-Header "Python wheelhouse (offline dependency cache)"
    $pythonExe = Join-Path $PythonDir "python.exe"
    if (-not (Test-Path $pythonExe)) {
        Write-Warn2 "bundled Python not found; skipping wheelhouse"
    } elseif (-not (Test-Path $Requirements)) {
        Write-Warn2 "requirements.txt not found at $Requirements; skipping wheelhouse"
    } else {
        if (Test-Path $Wheelhouse) { Remove-Item $Wheelhouse -Recurse -Force }
        New-Item -ItemType Directory -Path $Wheelhouse -Force | Out-Null
        & $pythonExe -m pip download -r $Requirements -d $Wheelhouse
        Write-Ok "wheels cached in wheelhouse\ ($((Get-ChildItem $Wheelhouse -File | Measure-Object).Count) files)"
    }
}

# ── 5. Warm the Maven repository (offline Java builds) ───────
if (-not $SkipMavenRepo) {
    Write-Header "Warming Maven repository (.m2-repo) for offline builds"
    $mvnCmd   = Join-Path $MavenDir "bin\mvn.cmd"
    $javaHome = $JavaDir
    if (-not (Test-Path $mvnCmd)) {
        Write-Warn2 "bundled Maven not found; skipping repo warm-up"
    } elseif (-not (Test-Path (Join-Path $javaHome "bin\java.exe"))) {
        Write-Warn2 "bundled JDK not found; skipping repo warm-up"
    } elseif (-not (Test-Path (Join-Path $JavaSvc "pom.xml"))) {
        Write-Warn2 "service pom.xml not found; skipping repo warm-up"
    } else {
        $env:JAVA_HOME = $javaHome
        $env:PATH = (Join-Path $javaHome "bin") + ";" + (Join-Path $MavenDir "bin") + ";" + $env:PATH
        New-Item -ItemType Directory -Path $MavenRepo -Force | Out-Null
        Write-Info "resolving Spring service dependencies (this can take a few minutes)"
        # go-offline + a real test pull plugins (surefire, spring-boot) into the bundled repo.
        & $mvnCmd -f (Join-Path $JavaSvc "pom.xml") "-Dmaven.repo.local=$MavenRepo" -q -DskipTests dependency:go-offline
        & $mvnCmd -f (Join-Path $JavaSvc "pom.xml") "-Dmaven.repo.local=$MavenRepo" -q test-compile
        if ($LASTEXITCODE -eq 0) { Write-Ok "Maven repo warmed -> .m2-repo\" }
        else { Write-Warn2 "repo warm-up returned exit code $LASTEXITCODE; first build on target may need internet" }
    }
}

# ── cleanup ──────────────────────────────────────────────────
if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }

Write-Header "Portable bundle ready"
Write-Host ""
Write-Host "  java\      -> $(if (Test-Path (Join-Path $JavaDir 'bin\java.exe')) {'Windows JDK'} else {'MISSING'})"
Write-Host "  maven\     -> $(if (Test-Path (Join-Path $MavenDir 'bin\mvn.cmd')) {'Apache Maven'} else {'MISSING'})"
Write-Host "  Python\    -> $(if (Test-Path (Join-Path $PythonDir 'python.exe')) {'CPython'} else {'MISSING'})"
Write-Host "  wheelhouse\-> $(if (Test-Path $Wheelhouse) {"$((Get-ChildItem $Wheelhouse -File -ErrorAction SilentlyContinue | Measure-Object).Count) wheels"} else {'none'})"
Write-Host "  .m2-repo\  -> $(if (Test-Path $MavenRepo) {'warmed'} else {'none'})"
Write-Host ""
Write-Host "  Next: zip this whole folder and share it. Recipient runs .\start.ps1" -ForegroundColor White
