param(
    [string]$PythonPath = 'python',
    [string]$NodePath = 'node',
    [string]$PwshPath = 'pwsh',
    [string]$NpmPath = 'npm.cmd'
)
$ErrorActionPreference = 'Stop'
function Resolve-Executable([string]$Name) {
    $command = Get-Command -Name $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1
    if (-not $command) { throw "Missing executable: $Name. Install it from its official source first." }
    return $command.Source
}
if ($env:OS -ne 'Windows_NT') { throw 'Windows is required for DPAPI and process-tree supervision.' }
$python = Resolve-Executable $PythonPath
$node = Resolve-Executable $NodePath
$pwsh = Resolve-Executable $PwshPath
$npm = Resolve-Executable $NpmPath
& $python -c "import sys; assert sys.version_info[:2] == (3,14), 'Python 3.14 is the tested version'"
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
$nodeVersion = & $node --version
if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v24\.') { throw 'Node.js 24 is the tested version.' }
$pwshVersion = & $pwsh -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.Major'
if ($LASTEXITCODE -ne 0 -or [int]$pwshVersion -lt 7) { throw 'PowerShell 7 or later is required.' }
$root = $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        & $python -m venv (Join-Path $root '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Local virtualenv creation failed.' }
    }
    & $venvPython -c "import sys; assert sys.version_info[:2] == (3,14), 'Existing virtualenv must use Python 3.14'"
    if ($LASTEXITCODE -ne 0) { throw 'Existing virtualenv has the wrong Python version; preserve it and review a manual replacement.' }
    & $venvPython -m pip --isolated install --index-url https://pypi.org/simple --disable-pip-version-check --require-hashes --only-binary=:all: -r (Join-Path $root 'requirements.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python dependency installation failed.' }
    # No lifecycle scripts, global installation or credential entry.
    & $npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
    if ($LASTEXITCODE -ne 0) { throw 'Locked Node dependency installation failed.' }
    & $venvPython -c 'import bridge; bridge.protect_state()'
    if ($LASTEXITCODE -ne 0) { throw 'Local state ACL setup failed.' }
    $launch = @{ node_path = $node; pwsh_path = $pwsh } | ConvertTo-Json
    [System.IO.File]::WriteAllText((Join-Path $root '.state\runtime-launch.json'), $launch)
    & $venvPython (Join-Path $root 'bridge.py') doctor
    if ($LASTEXITCODE -ne 0) { throw 'Offline initialization failed; no permission fallback performed.' }
} finally { Pop-Location }
