#Requires -RunAsAdministrator
[CmdletBinding()]
param(
  [string]$IsoPath = "C:\Source\GITHUB\MLOKAS2408\fosos\output\FosOS-trixie-amd64.iso",
  [string]$VmName = "FosOS"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $IsoPath)) {
  throw "ISO not found: $IsoPath"
}

$vm = Get-VM -Name $VmName -ErrorAction Stop
Write-Host "VM: $($vm.Name) state=$($vm.State)"
Write-Host "ISO: $IsoPath ($([math]::Round((Get-Item $IsoPath).Length/1MB)) MB, $((Get-Item $IsoPath).LastWriteTime))"

if ($vm.State -ne "Off") {
  Write-Host "Turning off VM..."
  Stop-VM -Name $VmName -Force -TurnOff
  Start-Sleep -Seconds 2
}

$dvd = Get-VMDvdDrive -VMName $VmName | Select-Object -First 1
if ($dvd) {
  Set-VMDvdDrive -VMName $VmName -ControllerNumber $dvd.ControllerNumber -ControllerLocation $dvd.ControllerLocation -Path $IsoPath
} else {
  Add-VMDvdDrive -VMName $VmName -Path $IsoPath
  $dvd = Get-VMDvdDrive -VMName $VmName | Select-Object -First 1
}

Set-VMFirmware -VMName $VmName -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority
$hdd = Get-VMHardDiskDrive -VMName $VmName | Select-Object -First 1
$boot = @()
if ($dvd) { $boot += $dvd }
if ($hdd) { $boot += $hdd }
if ($boot.Count -gt 0) {
  Set-VMFirmware -VMName $VmName -BootOrder $boot
}

Start-VM -Name $VmName
Start-Process vmconnect.exe -ArgumentList @("localhost", $VmName)
Get-VM -Name $VmName | Format-List Name, State, Status, @{N='MemoryMB';E={$_.MemoryAssigned/1MB}}
Write-Host "Secure Boot on (MicrosoftUEFICertificateAuthority); DVD first. Connect window should open."
