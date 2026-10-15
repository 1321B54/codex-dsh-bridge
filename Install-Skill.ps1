param([string]$SkillRoot = (Join-Path $HOME '.agents\skills'))
$ErrorActionPreference = 'Stop'
if (-not [System.IO.Path]::IsPathRooted($SkillRoot)) { throw 'SkillRoot must be absolute.' }
$destination = Join-Path $SkillRoot 'dsh-collaboration'
# Existing installations may belong to another project and must never be overwritten.
if (Test-Path -LiteralPath $destination) { throw 'A skill already exists here. Preserve it; choose another SkillRoot or review a manual replacement.' }
$source = Join-Path $PSScriptRoot 'skills\dsh-collaboration'
$files = @('SKILL.md','agents\openai.yaml','scripts\invoke-dsh.ps1','scripts\invoke-dsh.sh','scripts\invoke-dsh.py','references\operations.md')
foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $file) -PathType Leaf)) { throw "Skill source is incomplete: $file" }
}
$stage = Join-Path $SkillRoot ('.dsh-skill-stage-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -ErrorAction Stop | Out-Null
foreach ($file in $files) {
    $target = Join-Path $stage $file
    New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination $target -ErrorAction Stop
}
$location = @{ bridge_root = [System.IO.Path]::GetFullPath($PSScriptRoot) } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $stage 'bridge-location.json'), $location)
# Directory.Move fails if the destination appeared concurrently; it never merges/overwrites.
# Failed staging is deliberately retained for operator inspection, not recursively deleted.
[System.IO.Directory]::Move($stage, $destination)
Write-Output 'User-level skill installed; no credential copied and no model request made.'
