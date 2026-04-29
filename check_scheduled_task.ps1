param(
  [string]$TaskName = "Job Scraper Fleet v2 - Weekday 4PM"
)

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
  Write-Host "Scheduled task not installed: $TaskName"
  exit 1
}

Get-ScheduledTaskInfo -TaskName $TaskName
