@echo off
REM ============================================================
REM  setup_python.bat - Script DUY NHAT thiet lap moi truong cho Video Tool v2
REM  - Kiem tra / cai Python >= 3.10 + pip + requirements.txt
REM  - Kiem tra / cai FFmpeg & FFprobe (Gyan.FFmpeg)
REM  - Dat san Python, FFmpeg va thu muc Video Tool vao User PATH
REM  - Cai per-user nen KHONG can quyen Admin
REM ============================================================
setlocal
chcp 65001 >nul 2>nul
title Thiet lap moi truong ^& PATH cho Video Tool v2
echo.
echo  Dang mo PowerShell de kiem tra, cai dat Python + FFmpeg va dat User PATH...
echo.

set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" set "PS_EXE=powershell"
set "SELF_BAT=%~f0"
set "SELF_DIR=%~dp0"

if "%~1"=="" (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -Command "$c=[System.IO.File]::ReadAllText($env:SELF_BAT,[System.Text.Encoding]::UTF8);$m='<#'+'PS_START#>';&([scriptblock]::Create($c.Substring($c.IndexOf($m)))) -InstallRequirements -InstallFFmpeg -Pause"
) else (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -Command "$c=[System.IO.File]::ReadAllText($env:SELF_BAT,[System.Text.Encoding]::UTF8);$m='<#'+'PS_START#>';&([scriptblock]::Create($c.Substring($c.IndexOf($m))))" %*
)

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    if "%~1"=="" (
        echo.
        echo  [!] Qua trinh cai dat ket thuc voi ma loi %EXIT_CODE%.
        pause
    )
)
exit /b %EXIT_CODE%

<#PS_START#>
[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12.8",
    [switch]$InstallRequirements,
    [switch]$InstallFFmpeg,
    [switch]$SkipRequirements,
    [switch]$SkipFFmpeg,
    [switch]$SkipToolPath,
    [switch]$UseWinget,
    [switch]$CheckOnly,
    [switch]$ForceReinstall,
    [switch]$Pause
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

try {
    $IsWindowsOS = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)
} catch {
    $IsWindowsOS = ($env:OS -eq "Windows_NT")
}

$script:PythonExe = $null
$ScriptDir = if ($env:SELF_DIR) {
    $env:SELF_DIR.TrimEnd("\")
} elseif ($MyInvocation.MyCommand.Path) {
    Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    (Get-Location).Path
}

function Write-Step { param([string]$Msg) Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Write-Warn { param([string]$Msg) Write-Host "  [!] $Msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$Msg) Write-Host "  [LOI] $Msg" -ForegroundColor Red }

function Exit-Script {
    param([int]$Code = 0)
    if ($Pause) {
        Write-Host ""
        Read-Host "Nhan Enter de dong cua so"
    }
    exit $Code
}

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @()
    )
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Exe @Arguments 2>&1 | Out-String
        $code = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
        return @{ Output = $output; ExitCode = $code }
    } catch {
        return @{ Output = ($_ | Out-String); ExitCode = 1 }
    } finally {
        $ErrorActionPreference = $oldEap
    }
}

function Refresh-Path {
    if (-not $IsWindowsOS) { return }
    try {
        $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $combined = @($user, $machine) | Where-Object { $_ } | ForEach-Object {
            [System.Environment]::ExpandEnvironmentVariables($_.TrimEnd(";"))
        }
        $env:Path = ($combined -join ";")
    } catch {
        Write-Warn "Khong refresh duoc PATH tu registry: $_"
    }
}

function Test-InUserPath {
    param([string]$Dir)
    if (-not $Dir -or -not $IsWindowsOS) { return $false }
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) { return $false }
    $parts = $userPath -split ";" | Where-Object { $_ } | ForEach-Object { $_.Trim().TrimEnd("\").ToLowerInvariant() }
    $target = $Dir.Trim().TrimEnd("\").ToLowerInvariant()
    return ($parts -contains $target)
}

function Add-ToUserPath {
    param(
        [string]$Dir,
        [switch]$Prepend
    )
    if (-not $Dir -or -not (Test-Path $Dir)) { return $false }
    if (-not $IsWindowsOS) {
        Write-Warn "Bo qua them PATH (chi ap dung tren Windows): $Dir"
        return $false
    }
    try {
        $cleanDir = (Resolve-Path $Dir).Path.TrimEnd("\")
        $targetNorm = $cleanDir.ToLowerInvariant()
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        $rawParts = if ($userPath) {
            @($userPath -split ";" | Where-Object { $_.Trim() -ne "" })
        } else {
            @()
        }

        $alreadyInPath = Test-InUserPath -Dir $cleanDir
        $needsMoveBeforeWinApps = $false
        if ($alreadyInPath -and $Prepend) {
            $targetIdx = -1
            $winAppsIdx = -1
            for ($i = 0; $i -lt $rawParts.Count; $i++) {
                $norm = $rawParts[$i].Trim().TrimEnd("\").ToLowerInvariant()
                if ($targetIdx -lt 0 -and $norm -eq $targetNorm) { $targetIdx = $i }
                if ($winAppsIdx -lt 0 -and $norm -like "*\microsoft\windowsapps*") { $winAppsIdx = $i }
            }
            if ($winAppsIdx -ge 0 -and $targetIdx -gt $winAppsIdx) {
                $needsMoveBeforeWinApps = $true
            }
        }

        if ($alreadyInPath -and -not $needsMoveBeforeWinApps) {
            Write-Ok "Da co san trong User PATH: $cleanDir"
            Refresh-Path
            return $true
        }
        if ($CheckOnly) {
            Write-Warn "(CheckOnly) Chua co (hoac can dua len dau) trong User PATH: $cleanDir"
            return $false
        }

        $filteredParts = @($rawParts | Where-Object {
            $_.Trim().TrimEnd("\").ToLowerInvariant() -ne $targetNorm
        })
        if ($Prepend) {
            $newParts = @($cleanDir) + $filteredParts
        } else {
            $newParts = $filteredParts + @($cleanDir)
        }
        $newPath = ($newParts -join ";")
        [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Ok "Da them vao User PATH (vinh vien): $cleanDir"
        Refresh-Path
        return $true
    } catch {
        Write-Warn "Khong them duoc vao User PATH: $_"
        return $false
    }
}

function Get-PythonVersionString {
    param([string]$Exe)
    try {
        if (-not $Exe -or -not (Test-Path $Exe)) { return $null }
        if ($Exe -like "*\Microsoft\WindowsApps\python*.exe") {
            $item = Get-Item $Exe -ErrorAction SilentlyContinue
            if (-not $item -or $item.Length -eq 0) { return $null }
        }
        $res = Invoke-NativeCapture -Exe $Exe -Arguments @("--version")
        if ($res.ExitCode -eq 0 -and $res.Output -match "Python\s+(\d+\.\d+\.\d+)") {
            return $Matches[1]
        }
    } catch { }
    return $null
}

function Test-PythonOk {
    param([hashtable]$Found)
    if (-not $Found) { return $false }
    try {
        $parts = $Found.Version -split "\."
        $major = [int]$parts[0]; $minor = [int]$parts[1]
        return ($major -gt 3 -or ($major -eq 3 -and $minor -ge 10))
    } catch { return $false }
}

function Find-Python {
    $candidates = @()
    $roots = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "$env:ProgramFiles\Python",
        "${env:ProgramFiles(x86)}\Python",
        "C:\Python314", "C:\Python313", "C:\Python312", "C:\Python311", "C:\Python310"
    )
    foreach ($root in $roots) {
        if ($root -and (Test-Path $root)) {
            Get-ChildItem -Path $root -Filter "python.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending |
                ForEach-Object { $candidates += $_.FullName }
        }
    }
    foreach ($name in @("python", "py", "python3")) {
        $cmds = Get-Command $name -All -ErrorAction SilentlyContinue
        foreach ($cmd in $cmds) {
            if ($cmd -and $cmd.Source) { $candidates += $cmd.Source }
        }
    }
    $seen = @{}
    $fallback = $null
    foreach ($exe in $candidates) {
        if (-not $exe) { continue }
        $key = $exe.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $ver = Get-PythonVersionString -Exe $exe
        if ($ver) {
            $realExe = $exe
            if ([System.IO.Path]::GetFileName($exe).ToLowerInvariant() -eq "py.exe") {
                try {
                    $res = Invoke-NativeCapture -Exe $exe -Arguments @("-c", "import sys; print(sys.executable)")
                    $resolved = ($res.Output).Trim()
                    if ($res.ExitCode -eq 0 -and $resolved -and (Test-Path $resolved)) {
                        $realExe = $resolved
                    }
                } catch { }
            }
            $entry = @{ Exe = $realExe; Version = $ver; Source = "PATH / cai san" }
            if (Test-PythonOk -Found $entry) {
                return $entry
            }
            if (-not $fallback) {
                $fallback = $entry
            }
        }
    }
    return $fallback
}

function Install-PythonFromWeb {
    param([string]$Version)
    if (-not $IsWindowsOS) {
        throw "Script cai dat chi chay tren Windows."
    }
    $is64 = [System.Environment]::Is64BitOperatingSystem
    $arch = if ($is64) { "amd64" } else { "win32" }
    $url = "https://www.python.org/ftp/python/$Version/python-$Version-$arch.exe"
    $tempDir = [System.IO.Path]::GetTempPath()
    $installer = Join-Path $tempDir "python-$Version-$arch.exe"

    Write-Step "Tai bo cai Python $Version ($arch) tu python.org"
    Write-Host "  URL: $url"
    try {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Warn "Invoke-WebRequest that bai, thu Start-BitsTransfer: $_"
        Start-BitsTransfer -Source $url -Destination $installer
    }
    if (-not (Test-Path $installer) -or (Get-Item $installer).Length -lt 1000000) {
        throw "Tai bo cai that bai hoac file qua nho: $installer"
    }
    Write-Ok "Da tai xong: $([math]::Round((Get-Item $installer).Length / 1MB, 1)) MB"

    Write-Step "Cai dat silent (per-user, tu add PATH, co pip)..."
    $proc = Start-Process -FilePath $installer -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "Include_pip=1", "Include_launcher=1" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "Bo cai Python tra ve exit code $($proc.ExitCode)."
    }
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    Write-Ok "Cai dat Python xong."
    Start-Sleep -Seconds 2
    Refresh-Path
}

function Install-PythonViaWinget {
    param([string]$Version)
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { throw "Khong tim thay winget tren may nay." }
    $mm = ($Version -split "\.")[0..1] -join "."
    Write-Step "Cai Python $mm bang winget..."
    $proc = Start-Process -FilePath "winget" -ArgumentList "install", "--id", "Python.Python.$mm", "-e", "--accept-source-agreements", "--accept-package-agreements", "--silent" -Wait -PassThru -NoNewWindow
    if ($proc.ExitCode -ne 0) { throw "winget tra ve exit code $($proc.ExitCode)." }
    Refresh-Path
}

function Install-RequirementsIfAny {
    $pyExe = if ($script:PythonExe) { $script:PythonExe } else { "python" }
    $req = Join-Path $ScriptDir "requirements.txt"
    if (-not (Test-Path $req)) {
        Write-Warn "Khong tim thay requirements.txt tai $ScriptDir - bo qua."
        return
    }
    Write-Step "Buoc 5: Cai thu vien Python tu $req"
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $pyExe -m pip install --upgrade pip --quiet 2>$null
        & $pyExe -m pip install -r $req
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            Write-Warn "Thu cai lai requirements.txt voi co --user..."
            & $pyExe -m pip install --user -r $req
            $code = $LASTEXITCODE
        }
        if ($code -eq 0) {
            Write-Ok "Da cai xong requirements.txt"
        } else {
            Write-Warn "Co loi khi cai requirements.txt (exit code $code)."
        }
    } finally {
        $ErrorActionPreference = $oldEap
    }
}

function Find-FFmpegBinDir {
    Refresh-Path
    $ffRoot = "$env:LOCALAPPDATA\Programs\ffmpeg"
    $searchRoots = @(
        (Join-Path $ffRoot "modern"),
        $ffRoot,
        "$env:USERPROFILE\ffmpeg",
        "C:\ffmpeg",
        "$env:ProgramFiles\ffmpeg",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages",
        "$env:ProgramData\chocolatey\lib\ffmpeg"
    )
    foreach ($root in $searchRoots) {
        if ($root -and (Test-Path $root)) {
            $foundExe = Get-ChildItem -Path $root -Filter "ffmpeg.exe" -Recurse -Depth 5 -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($foundExe) {
                $dir = Split-Path -Parent $foundExe.FullName
                if (Test-Path (Join-Path $dir "ffprobe.exe")) {
                    return $dir
                }
            }
        }
    }
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
        $dir = Split-Path -Parent $cmd.Source
        if (Test-Path (Join-Path $dir "ffprobe.exe")) {
            return $dir
        }
    }
    return $null
}

function Test-NvencNeedsLegacyFFmpeg {
    param([string]$FFmpegExe)
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $smi -or -not $FFmpegExe -or -not (Test-Path $FFmpegExe)) { return $false }
    $res = Invoke-NativeCapture -Exe $FFmpegExe -Arguments @("-y", "-v", "info", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30", "-an", "-pix_fmt", "yuv420p", "-c:v", "h264_nvenc", "-f", "null", "-")
    if ($res.ExitCode -ne 0 -and $res.Output -match "Driver does not support the required nvenc API version") {
        return $true
    }
    return $false
}

function Install-FFmpegPortableZip {
    param([switch]$LegacyNvenc)
    $destRoot = Join-Path $env:LOCALAPPDATA "Programs\ffmpeg"
    $profile = if ($LegacyNvenc) { "legacy" } else { "modern" }
    $destProfile = Join-Path $destRoot $profile
    $url = if ($LegacyNvenc) {
        "https://github.com/GyanD/codexffmpeg/releases/download/5.1.2/ffmpeg-5.1.2-essentials_build.zip"
    } else {
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    }
    $zipName = if ($LegacyNvenc) { "ffmpeg-5.1.2-essentials_build.zip" } else { "ffmpeg-release-essentials.zip" }
    $zipPath = Join-Path ([System.IO.Path]::GetTempPath()) $zipName
    Write-Step "Tai FFmpeg $profile tu $url ..."
    try {
        Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    } catch {
        Start-BitsTransfer -Source $url -Destination $zipPath
    }
    if (-not (Test-Path $zipPath) -or (Get-Item $zipPath).Length -lt 10000000) {
        throw "Tai FFmpeg zip that bai."
    }
    if (Test-Path $destProfile) {
        Remove-Item $destProfile -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $destProfile -Force | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $destProfile -Force
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
    $exe = Get-ChildItem -Path $destProfile -Filter "ffmpeg.exe" -Recurse -Depth 5 |
        Select-Object -First 1
    if (-not $exe) { throw "Khong tim thay ffmpeg.exe sau khi giai nen." }
    return (Split-Path -Parent $exe.FullName)
}

function Ensure-FFmpeg {
    param([bool]$AutoInstall)
    $ffDir = Find-FFmpegBinDir
    if ($ffDir) {
        $ffExe = Join-Path $ffDir "ffmpeg.exe"
        if (-not $CheckOnly -and $AutoInstall -and (Test-NvencNeedsLegacyFFmpeg -FFmpegExe $ffExe)) {
            Write-Warn "FFmpeg hien tai yeu cau NVENC API moi hon driver NVIDIA tren may -> Tai them FFmpeg 5.1.2 tuong thich..."
            try {
                $ffDir = Install-FFmpegPortableZip -LegacyNvenc
            } catch {
                Write-Warn "Khong tai duoc FFmpeg 5.1.2: $_"
            }
        }
        Write-Ok "Da tim thay FFmpeg + FFprobe tai: $ffDir"
        Add-ToUserPath -Dir $ffDir -Prepend | Out-Null
        return $ffDir
    }
    if ($CheckOnly -or -not $AutoInstall) {
        Write-Warn "Chua co FFmpeg tren may (bat buoc cho Video Tool). Chay setup_python.bat de tu dong cai va add PATH."
        return $null
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Step "Chua co FFmpeg -> Dang tu dong cai Gyan.FFmpeg bang winget..."
        $proc = Start-Process -FilePath "winget" -ArgumentList "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements", "--silent" -Wait -PassThru -NoNewWindow
        Refresh-Path
        $ffDir = Find-FFmpegBinDir
        if ($ffDir) {
            $ffExe = Join-Path $ffDir "ffmpeg.exe"
            if (Test-NvencNeedsLegacyFFmpeg -FFmpegExe $ffExe) {
                Write-Warn "FFmpeg tu winget yeu cau NVENC API moi hon driver NVIDIA -> Tai them FFmpeg 5.1.2 tuong thich..."
                $ffDir = Install-FFmpegPortableZip -LegacyNvenc
            }
            Write-Ok "Da cai xong FFmpeg tai: $ffDir"
            Add-ToUserPath -Dir $ffDir -Prepend | Out-Null
            return $ffDir
        }
        Write-Warn "winget ket thuc (code $($proc.ExitCode)) nhung chua thay ffmpeg, chuyen sang tai ban zip portable..."
    }
    try {
        $ffDir = Install-FFmpegPortableZip
        if ($ffDir) {
            $ffExe = Join-Path $ffDir "ffmpeg.exe"
            if (Test-NvencNeedsLegacyFFmpeg -FFmpegExe $ffExe) {
                $ffDir = Install-FFmpegPortableZip -LegacyNvenc
            }
            Write-Ok "Da cai xong FFmpeg portable tai: $ffDir"
            Add-ToUserPath -Dir $ffDir -Prepend | Out-Null
            return $ffDir
        }
    } catch {
        Write-Err "Khong the tu dong cai FFmpeg: $_"
    }
    return $null
}

# ================= CHUONG TRINH CHINH =================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Thiet lap moi truong & PATH cho Video Tool v2" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Thu muc tool: $ScriptDir"

if ($CheckOnly) {
    Write-Step "Che do CheckOnly: chi kiem tra, khong tai / khong cai / khong sua PATH."
}

# --- Buoc 1 & 2: Python ---
Write-Step "Buoc 1: Kiem tra Python (>= 3.10)"
$found = Find-Python
if ($found -and -not $ForceReinstall) {
    Write-Ok "Da tim thay Python $($found.Version) tai: $($found.Exe)"
    if (Test-PythonOk -Found $found) {
        Write-Ok "Phien ban Python dat yeu cau (>= 3.10)."
    } else {
        Write-Warn "Python $($found.Version) qua cu (< 3.10). Se cai ban moi $PythonVersion."
        $found = $null
    }
} elseif ($found -and $ForceReinstall) {
    Write-Warn "Da co Python $($found.Version) nhung chon -ForceReinstall nen se cai lai."
    $found = $null
} else {
    Write-Warn "Chua tim thay Python tren may."
}

if (-not $found) {
    if ($CheckOnly) {
        Write-Err "KET LUAN (CheckOnly): Chua co Python >= 3.10."
        Exit-Script -Code 2
    }
    try {
        if ($UseWinget) {
            Install-PythonViaWinget -Version $PythonVersion
        } else {
            Install-PythonFromWeb -Version $PythonVersion
        }
    } catch {
        Write-Err "Loi khi cai dat Python: $_"
        Exit-Script -Code 1
    }
    Write-Step "Buoc 2: Kiem tra lai Python sau khi cai"
    Refresh-Path
    $found = Find-Python
    if (-not $found) {
        Write-Err "Van khong tim thay Python sau khi cai. Hay mo CMD/PowerShell moi hoac chay bang Run as Administrator."
        Exit-Script -Code 1
    }
    Write-Ok "Da cai xong Python $($found.Version) tai: $($found.Exe)"
}

$script:PythonExe = $found.Exe

# --- Buoc 3: Add Python vao User PATH (Prepend de dung truoc WindowsApps stub) ---
Write-Step "Buoc 3: Dat Python va Scripts vao User PATH"
$pyDir = Split-Path -Parent $found.Exe
$scriptsDir = Join-Path $pyDir "Scripts"
Add-ToUserPath -Dir $scriptsDir -Prepend | Out-Null
Add-ToUserPath -Dir $pyDir -Prepend | Out-Null
$launcherDir = Join-Path (Split-Path -Parent $pyDir) "Launcher"
if (Test-Path $launcherDir) {
    Add-ToUserPath -Dir $launcherDir | Out-Null
}

# --- Buoc 4: Kiem tra pip ---
Write-Step "Buoc 4: Kiem tra pip"
$pipOk = $false
$pipRes = Invoke-NativeCapture -Exe $script:PythonExe -Arguments @("-m", "pip", "--version")
if ($pipRes.ExitCode -eq 0 -and $pipRes.Output -match "pip") {
    Write-Ok "pip: $($pipRes.Output.Trim())"
    $pipOk = $true
}
if (-not $pipOk -and -not $CheckOnly) {
    Write-Warn "Chua co pip, dang cai bang ensurepip..."
    $ensRes = Invoke-NativeCapture -Exe $script:PythonExe -Arguments @("-m", "ensurepip", "--upgrade")
    $pipRes2 = Invoke-NativeCapture -Exe $script:PythonExe -Arguments @("-m", "pip", "--version")
    if ($pipRes2.ExitCode -eq 0 -and $pipRes2.Output -match "pip") {
        Write-Ok "pip: $($pipRes2.Output.Trim())"
    } else {
        Write-Warn "Khong cai duoc pip: $($ensRes.Output.Trim())"
    }
}

# --- Buoc 5: Cai requirements.txt (mac dinh chay khi khong CheckOnly va khong SkipRequirements) ---
$doReqs = (-not $SkipRequirements) -and ($InstallRequirements -or (-not $CheckOnly))
if ($doReqs -and -not $CheckOnly) {
    Install-RequirementsIfAny
}

# --- Buoc 6: Kiem tra / Cai FFmpeg + add vao User PATH ---
Write-Step "Buoc 6: Kiem tra FFmpeg & FFprobe va dat vao User PATH"
$doFFmpeg = (-not $SkipFFmpeg) -and ($InstallFFmpeg -or (-not $CheckOnly))
$ffBinDir = Ensure-FFmpeg -AutoInstall:$doFFmpeg

# --- Buoc 7: Dat thu muc Video Tool vao User PATH ---
Write-Step "Buoc 7: Dat thu muc Video Tool vao User PATH (lenh video-tool)"
if (-not $SkipToolPath) {
    Add-ToUserPath -Dir $ScriptDir | Out-Null
} else {
    Write-Warn "Bo qua them thu muc tool vao PATH (-SkipToolPath)."
}

Refresh-Path

# --- Buoc 8: Kiem tra tong the ---
Write-Step "Buoc 8: Xac minh moi truong chay"
$pyVerRes = Invoke-NativeCapture -Exe $script:PythonExe -Arguments @("--version")
$pyVer = ($pyVerRes.Output).Trim()
$ffCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
$fpCmd = Get-Command ffprobe -ErrorAction SilentlyContinue
$vtCmd = Get-Command video-tool -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  HOAN TAT THIET LAP MOI TRUONG" -ForegroundColor Green
Write-Host "  Python     : $pyVer ($($found.Exe))" -ForegroundColor Green
if ($ffCmd -and $fpCmd) {
    Write-Host "  FFmpeg     : $($ffCmd.Source)" -ForegroundColor Green
    Write-Host "  FFprobe    : $($fpCmd.Source)" -ForegroundColor Green
} else {
    Write-Host "  FFmpeg     : CHUA CO (hay cai FFmpeg de chay xu ly video)" -ForegroundColor Yellow
}
if ($vtCmd) {
    Write-Host "  Lenh PATH  : video-tool ($($vtCmd.Source))" -ForegroundColor Green
} else {
    Write-Host "  Thu muc PATH: $ScriptDir" -ForegroundColor Green
}
Write-Host "------------------------------------------------------------" -ForegroundColor Green
Write-Host "  Cach chay tool (mo CMD / PowerShell MOI hoac double-click):" -ForegroundColor Green
Write-Host "    video-tool                  (mo giao dien GUI tu bat ky dau)" -ForegroundColor Green
Write-Host "    video-tool gpu              (quet GPU & encoder)" -ForegroundColor Green
Write-Host "    video-tool info -i a.mp4    (xem thong so chi tiet)" -ForegroundColor Green
Write-Host "    python main.py              (chay truc tiep trong thu muc)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

Exit-Script -Code 0
