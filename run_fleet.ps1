param(
  [switch]$IncludeLinkedIn,     # opt in to LinkedIn's public job search (against LinkedIn's terms; off by default)
  [switch]$SkipLLM,             # no Claude calls this run (scout + triage)
  [switch]$ForceScout,          # run the weekly Claude company scout now
  [switch]$SkipCompanyScout,    # skip the weekly scout this run
  [switch]$DiscoverBoards,      # manual: free web search for new ATS boards, then verify
  [switch]$IncludeSearch,       # also expand seed URLs found by free web search
  [switch]$SkipDiscoverBoards,  # v2 compatibility; search discovery is now off by default
  [int]$MaxPerCategory = 40
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# Prefer the project's locked virtual environment (created once with `uv sync`).
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  $python = if ($cmd) { $cmd.Source } else { $null }
}
if (-not $python) {
  Write-Error "Python not found. Install Python 3.11+ and run 'uv sync' (or 'pip install -r requirements.txt')."
  exit 2
}

$argsList = @(
  "-m", "jobfleet.cli",
  "--config-dir", (Join-Path $root "config"),
  "--output-dir", (Join-Path $root "outputs"),
  "--max-per-category", $MaxPerCategory
)
if ($IncludeLinkedIn)  { $argsList += "--include-linkedin" }
if ($SkipLLM)          { $argsList += "--skip-llm" }
if ($ForceScout)       { $argsList += "--force-scout" }
if ($SkipCompanyScout) { $argsList += "--skip-scout" }
if ($DiscoverBoards)   { $argsList += "--discover-boards" }
if ($IncludeSearch)    { $argsList += "--include-search" }

$started = Get-Date
& $python @argsList
$code = $LASTEXITCODE

# One line per run so failed scheduled runs are visible even if Python died before logging started.
$logDir = Join-Path $root "outputs\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
"{0:u}  exit={1}  duration={2:n0}s  python={3}" -f $started, $code, ((Get-Date) - $started).TotalSeconds, $python |
  Out-File -FilePath (Join-Path $logDir "scheduler_runs.log") -Append -Encoding utf8

exit $code
