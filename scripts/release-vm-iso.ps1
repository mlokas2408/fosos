<#
.SYNOPSIS
  Pull FosOS on the dedicated Debian 13 release VM, optionally build the ISO,
  and copy it back to this machine's output/ folder.

.DESCRIPTION
  Development stays on this PC. Release ISOs are built on a clean Debian 13 VM
  (see docs/BUILDING.md). This helper SSHs to that VM, updates the checkout,
  runs check-build-config + build-iso, then scp's the hybrid ISO home.

  Does nothing destructive to the VM beyond git pull --ff-only and live-build.

.EXAMPLE
  # Full release build + fetch ISO (long-running)
  .\scripts\release-vm-iso.ps1

.EXAMPLE
  # Sync + config check only (no lb build)
  .\scripts\release-vm-iso.ps1 -SkipBuild

.EXAMPLE
  .\scripts\release-vm-iso.ps1 -HostName 10.0.99.203 -User amagi -SkipFetch
#>
[CmdletBinding()]
param(
  [string]$HostName = $(if ($env:FOSOS_RELEASE_VM) { $env:FOSOS_RELEASE_VM } else { "10.0.99.203" }),
  [string]$User = $(if ($env:FOSOS_RELEASE_USER) { $env:FOSOS_RELEASE_USER } else { "amagi" }),
  [string]$RemoteRepo = $(if ($env:FOSOS_RELEASE_REPO) { $env:FOSOS_RELEASE_REPO } else { "~/fosos" }),
  [string]$Branch = "main",
  [string]$LocalIsoDir = "",
  [switch]$SkipBuild,
  [switch]$SkipFetch,
  [switch]$SkipPull
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $LocalIsoDir) {
  $LocalIsoDir = Join-Path $repoRoot "output"
}

$sshTarget = "${User}@${HostName}"
$sshOpts = @(
  "-o", "BatchMode=yes",
  "-o", "ConnectTimeout=15",
  "-o", "StrictHostKeyChecking=accept-new"
)

function Invoke-Remote {
  param([Parameter(Mandatory)][string]$RemoteCommand)
  Write-Host ">> ssh $sshTarget -- $RemoteCommand"
  & ssh @sshOpts $sshTarget $RemoteCommand
  if ($LASTEXITCODE -ne 0) {
    throw "Remote command failed (exit $LASTEXITCODE): $RemoteCommand"
  }
}

Write-Host "Release VM: $sshTarget"
Write-Host "Remote repo: $RemoteRepo (branch $Branch)"

# Probe SSH before a long build.
Invoke-Remote "grep VERSION_CODENAME /etc/os-release && test -d $RemoteRepo/.git && echo repo-ok"

if (-not $SkipPull) {
  Invoke-Remote @"
set -euo pipefail
cd $RemoteRepo
git fetch origin '$Branch'
git checkout '$Branch'
git pull --ff-only origin '$Branch'
git log -1 --oneline
"@
}

Invoke-Remote "cd $RemoteRepo && sudo bash scripts/check-build-config.sh"

if (-not $SkipBuild) {
  Write-Host "Starting ISO build on the VM (this can take a long time)..."
  Invoke-Remote "cd $RemoteRepo && sudo bash scripts/build-iso.sh"
} else {
  Write-Host "SkipBuild set; not running build-iso.sh."
}

$remoteIso = "$RemoteRepo/output/FosOS-trixie-amd64.iso"

if (-not $SkipFetch) {
  if ($SkipBuild) {
    # Still allow fetching an existing ISO after a check-only run.
    Invoke-Remote "test -f $remoteIso"
  }
  New-Item -ItemType Directory -Force -Path $LocalIsoDir | Out-Null
  $localIso = Join-Path $LocalIsoDir "FosOS-trixie-amd64.iso"
  Write-Host "Fetching $remoteIso -> $localIso"
  & scp @sshOpts "${sshTarget}:${remoteIso}" $localIso
  if ($LASTEXITCODE -ne 0) {
    throw "scp failed (exit $LASTEXITCODE)"
  }
  $item = Get-Item -LiteralPath $localIso
  Write-Host ("ISO ready: {0} ({1:N1} MB, {2})" -f $item.FullName, ($item.Length / 1MB), $item.LastWriteTime)
} else {
  Write-Host "SkipFetch set; ISO left on VM at $remoteIso"
}

Write-Host "Done."
