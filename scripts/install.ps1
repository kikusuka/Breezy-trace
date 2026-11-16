# Install Breezy Trace as a uv tool on Windows.
[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$WithCode
)

$ErrorActionPreference = "Stop"
$UvInstallUrl = "https://astral.sh/uv/install.ps1"
$PackageName = "breezy-trace"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Fail "Could not enable TLS 1.2: $($_.Exception.Message)"
}

function Get-UvPath {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }
    return $null
}

$Uv = Get-UvPath
if (-not $Uv) {
    Write-Step "Installing uv..."
    try {
        Invoke-RestMethod -Uri $UvInstallUrl | Invoke-Expression
    } catch {
        Fail "Could not install uv: $($_.Exception.Message)"
    }

    $installDirs = @()
    if ($env:UV_INSTALL_DIR) { $installDirs += $env:UV_INSTALL_DIR }
    if ($env:XDG_BIN_HOME) { $installDirs += $env:XDG_BIN_HOME }
    $installDirs += (Join-Path $HOME ".local\bin")
    foreach ($dir in $installDirs) {
        if ($dir -and (Test-Path -LiteralPath $dir)) {
            $env:Path = "$dir;$env:Path"
        }
    }

    $Uv = Get-UvPath
    if (-not $Uv -and $env:UV_INSTALL_DIR) {
        $candidate = Join-Path $env:UV_INSTALL_DIR "uv.exe"
        if (Test-Path -LiteralPath $candidate) { $Uv = $candidate }
    }
    if (-not $Uv) {
        $candidate = Join-Path (Join-Path $HOME ".local") "bin\uv.exe"
        if (Test-Path -LiteralPath $candidate) { $Uv = $candidate }
    }
    if (-not $Uv) {
        Fail "uv was installed but is not available on PATH. Restart your terminal and run this installer again."
    }
}

$Package = $PackageName
if ($WithCode) { $Package = "breezy-trace[code]" }
$Version = $Version.Trim()
if ($Version.StartsWith("v")) { $Version = $Version.Substring(1) }
if ($Version) { $Package = "$Package==$Version" }

Write-Step "Installing $Package..."
& $Uv tool install --upgrade $Package
if ($LASTEXITCODE -ne 0) {
    Fail "uv could not install Breezy Trace (exit code $LASTEXITCODE)."
}

$ToolBin = ""
$toolBinOutput = & $Uv tool dir --bin
if ($LASTEXITCODE -eq 0 -and $toolBinOutput) {
    $ToolBin = ([string]($toolBinOutput | Select-Object -First 1)).Trim()
}
if (-not $ToolBin) {
    if ($env:UV_TOOL_BIN_DIR) {
        $ToolBin = $env:UV_TOOL_BIN_DIR
    } else {
        $ToolBin = Join-Path $HOME ".local\bin"
    }
}
if ($ToolBin) {
    $env:Path = "$ToolBin;$env:Path"
}

if ($env:UV_NO_MODIFY_PATH -and $env:UV_NO_MODIFY_PATH -ne "0") {
    Write-Host "Skipping shell PATH update because UV_NO_MODIFY_PATH is set."
} else {
    Write-Step "Adding the Breezy Trace command to your PATH..."
    & $Uv tool update-shell
    if ($LASTEXITCODE -ne 0) {
        Write-Host "warning: uv could not update your shell PATH automatically." -ForegroundColor Yellow
        Write-Host "Add $ToolBin to your PATH, or run: $Uv tool update-shell"
    }
}

$Exe = Join-Path $ToolBin "breezy-trace.exe"
if (-not (Test-Path -LiteralPath $Exe)) {
    $command = Get-Command breezy-trace -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        $Exe = $command.Source
    } else {
        Fail "Breezy Trace was installed, but $Exe was not found."
    }
}

Write-Step "Verifying the install..."
& $Exe --version
if ($LASTEXITCODE -ne 0) {
    Fail "breezy-trace --version failed. Open a new terminal and run: breezy-trace --version"
}

Write-Host ""
Write-Host "Breezy Trace is ready." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Restart your terminal (or open a new PowerShell window) so the breezy-trace command is available."
Write-Host "  2. Run: breezy-trace"
Write-Host "  3. Later, check for updates with: breezy-trace update --check"
Write-Host "     and upgrade with: breezy-trace update"
if ($WithCode) {
    Write-Host "Optional multi-language indexing is installed."
} else {
    Write-Host "Optional multi-language indexing: run this installer again with -WithCode."
}
