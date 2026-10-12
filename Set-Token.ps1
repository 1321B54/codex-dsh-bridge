$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Local DSH runtime is missing.' }
& $python (Join-Path $PSScriptRoot 'bridge.py') set-token
if ($LASTEXITCODE -ne 0) { throw 'Credential was not configured.' }
