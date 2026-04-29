param(
  [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputs = Join-Path $root "outputs"
$researchDir = Join-Path $outputs "research"
$logsDir = Join-Path $outputs "logs"
$schema = Join-Path $root "config\company_scout_schema.json"
$prompt = Join-Path $root "config\company_scout_prompt.md"
$latest = Join-Path $researchDir "company_candidates_latest.json"
$dated = Join-Path $researchDir ("company_candidates_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$log = Join-Path $logsDir ("company_scout_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

New-Item -ItemType Directory -Force $researchDir, $logsDir | Out-Null

$codex = Get-Command codex.cmd -ErrorAction SilentlyContinue
if ($null -eq $codex) {
  Write-Warning "codex.cmd was not found. Skipping company scout."
  exit 0
}

$job = Start-Job -ScriptBlock {
  param($root, $schema, $latest, $prompt)
  Get-Content -Raw -LiteralPath $prompt | codex.cmd `
    --search `
    exec `
    --skip-git-repo-check `
    --cd $root `
    --output-schema $schema `
    --output-last-message $latest `
    -
} -ArgumentList $root, $schema, $latest, $prompt

$completed = Wait-Job $job -Timeout $TimeoutSeconds
if ($null -eq $completed) {
  Stop-Job $job | Out-Null
  Receive-Job $job -ErrorAction SilentlyContinue *>&1 | Out-File -FilePath $log -Encoding utf8
  Remove-Job $job -Force
  Write-Warning "Company scout timed out after $TimeoutSeconds seconds. Continuing with existing sources."
  exit 0
}

Receive-Job $job -ErrorAction SilentlyContinue *>&1 | Out-File -FilePath $log -Encoding utf8
Remove-Job $job

if (-not (Test-Path -LiteralPath $latest)) {
  Write-Warning "Company scout did not create an output file. Continuing with existing sources."
  exit 0
}

try {
  $json = Get-Content -Raw -LiteralPath $latest | ConvertFrom-Json
  if ($null -eq $json.companies) {
    throw "Missing companies array."
  }
  Copy-Item -LiteralPath $latest -Destination $dated -Force
  Write-Host "Company scout wrote: $latest"
}
catch {
  Write-Warning "Company scout output was not valid JSON: $($_.Exception.Message)"
  exit 0
}
