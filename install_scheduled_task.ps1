param(
  [string]$TaskName = "Job Scraper Fleet v2 - Weekday 4PM",
  [string]$StartTime = "16:00"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $root "run_fleet.ps1"

if (-not (Test-Path -LiteralPath $runner)) {
  throw "Runner not found: $runner"
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""

$trigger = New-ScheduledTaskTrigger `
  -Weekly `
  -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
  -At $StartTime

$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
  -RestartCount 2 `
  -RestartInterval (New-TimeSpan -Minutes 10) `
  -RunOnlyIfNetworkAvailable

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
  -UserId $currentUser `
  -LogonType Interactive `
  -RunLevel Limited

$task = New-ScheduledTask `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Description "Runs Job Scraper Fleet v2 every weekday at 4 PM. If the machine is off or unavailable, Task Scheduler starts it when available after login."

Register-ScheduledTask `
  -TaskName $TaskName `
  -InputObject $task `
  -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Schedule: Monday-Friday at $StartTime"
Write-Host "Runner: $runner"
Write-Host "Missed starts: enabled via StartWhenAvailable"
