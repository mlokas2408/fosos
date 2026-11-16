#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Create or refresh a FosOS Gen2 Hyper-V VM and boot the development ISO.
#>
[CmdletBinding()]
param(
  [string]$IsoPath = "C:\Source\GITHUB\MLOKAS2408\fosos\output\FosOS-trixie-amd64.iso",
  [string]$VmName = "FosOS-Test",
  [string]$VmPath = "C:\Hyper-V\FosOS-Test",
  [int64]$MemoryBytes = 4GB,
  [int]$ProcessorCount = 2,
  [int64]$DiskBytes = 32GB,
  [switch]$InstallDisk
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $IsoPath)) {
  throw "ISO not found: $IsoPath"
}

Write-Host "ISO: $IsoPath ($([math]::Round((Get-Item $IsoPath).Length / 1MB)) MB)"

$existing = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Stopping existing VM '$VmName'..."
  if ($existing.State -ne "Off") {
    Stop-VM -Name $VmName -Force -TurnOff
  }
  # Detach and remove DVD / disks we manage, then recreate cleanly.
  Get-VMDvdDrive -VMName $VmName | Remove-VMDvdDrive -ErrorAction SilentlyContinue
  Get-VMHardDiskDrive -VMName $VmName | ForEach-Object {
    $path = $_.Path
    Remove-VMHardDiskDrive -VMName $VmName -ControllerType $_.ControllerType -ControllerNumber $_.ControllerNumber -ControllerLocation $_.ControllerLocation
    if ($path -and (Test-Path -LiteralPath $path) -and $path -like "*$VmName*") {
      Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
  }
  Remove-VM -Name $VmName -Force
}

New-Item -ItemType Directory -Force -Path $VmPath | Out-Null
$vhdx = Join-Path $VmPath "$VmName.vhdx"

Write-Host "Creating Generation 2 VM '$VmName'..."
New-VM -Name $VmName -Generation 2 -MemoryStartupBytes $MemoryBytes -Path $VmPath -NoVHD | Out-Null
Set-VMProcessor -VMName $VmName -Count $ProcessorCount
Set-VMFirmware -VMName $VmName -EnableSecureBoot Off
Set-VMMemory -VMName $VmName -DynamicMemoryEnabled $false

if ($InstallDisk) {
  Write-Host "Creating $([math]::Round($DiskBytes/1GB)) GB VHDX for install test..."
  New-VHD -Path $vhdx -SizeBytes $DiskBytes -Dynamic | Out-Null
  Add-VMHardDiskDrive -VMName $VmName -Path $vhdx
}

Add-VMDvdDrive -VMName $VmName -Path $IsoPath

# Prefer Default Switch when present; else first external/internal switch.
$switch = Get-VMSwitch | Where-Object { $_.Name -eq "Default Switch" } | Select-Object -First 1
if (-not $switch) {
  $switch = Get-VMSwitch | Select-Object -First 1
}
if ($switch) {
  Connect-VMNetworkAdapter -VMName $VmName -SwitchName $switch.Name
  Write-Host "Network: $($switch.Name)"
} else {
  Write-Warning "No virtual switch found; VM will have no network."
}

$dvd = Get-VMDvdDrive -VMName $VmName | Select-Object -First 1
$hdd = Get-VMHardDiskDrive -VMName $VmName | Select-Object -First 1
$bootOrder = @()
if ($dvd) { $bootOrder += $dvd }
if ($hdd) { $bootOrder += $hdd }
Set-VMFirmware -VMName $VmName -BootOrder $bootOrder -EnableSecureBoot Off

Write-Host "Starting VM..."
Start-VM -Name $VmName
Start-Process vmconnect.exe -ArgumentList @("localhost", $VmName)

Get-VM -Name $VmName | Format-List Name, State, Generation, @{N='MemoryMB';E={$_.MemoryStartup/1MB}}, ProcessorCount, Status
Write-Host "Done. Secure Boot is off; DVD is first in boot order."
