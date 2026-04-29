param(
  [switch]$IncludeSearch,
  [switch]$SkipCompanyScout,
  [switch]$SkipDiscoverBoards,
  [int]$MaxPerCategory = 40
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root "src"
$companyCandidates = Join-Path $root "outputs\research\company_candidates_latest.json"
$runStartedAt = Get-Date

if (-not $SkipCompanyScout) {
  try {
    & (Join-Path $root "run_company_scout.ps1")
  }
  catch {
    Write-Warning "Company scout failed. Continuing with existing sources. $($_.Exception.Message)"
  }
}

$argsList = @(
  "--config-dir", (Join-Path $root "config"),
  "--output-dir", (Join-Path $root "outputs"),
  "--max-per-category", $MaxPerCategory
)

if ($IncludeSearch) {
  $argsList += "--include-search"
}

if ($SkipDiscoverBoards) {
  $argsList += "--skip-discover-boards"
}

if ((Test-Path -LiteralPath $companyCandidates) -and ((Get-Item -LiteralPath $companyCandidates).LastWriteTime -ge $runStartedAt)) {
  $argsList += "--company-candidates"
  $argsList += $companyCandidates
}

python -m jobfleet.cli @argsList
