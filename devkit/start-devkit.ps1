param([string]$Python = '', [string]$CompilerArchive = '', [string]$WheelDirectory = '', [ValidateRange(2,8)][int]$Players = 3,
      [ValidateSet('', 'bomberman', 'gomoku')][string]$Game = '')
$ErrorActionPreference = 'Stop'
$taskRoot = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'arena.py')) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
Push-Location -LiteralPath $taskRoot
try {
    if (-not $Game) {
        $Game = 'bomberman'
        if (Test-Path -LiteralPath 'devkit-manifest.json') {
            $taskManifest = Get-Content -Raw -LiteralPath 'devkit-manifest.json' | ConvertFrom-Json
            if ($taskManifest.game_id -eq 'gomoku') { $Game = 'gomoku' }
        }
    }
    if ($Game -eq 'gomoku') {
        if ($PSBoundParameters.ContainsKey('Players') -and $Players -ne 2) { throw 'Gomoku requires two players.' }
        $Players = 2
    }
    $taskEnvironment = Join-Path $taskRoot '.venv\Scripts\python.exe'
    $taskReady = $false
    if (Test-Path -LiteralPath $taskEnvironment) {
        & $taskEnvironment tools\devkit_ready.py
        $taskReady = $LASTEXITCODE -eq 0
    }
    if (-not $taskReady) {
        & (Join-Path $taskRoot 'tools\setup.ps1') -Python $Python -CompilerArchive $CompilerArchive -WheelDirectory $WheelDirectory
    }
    $taskPreflight = 'artifacts/work/preflight-' + [guid]::NewGuid().ToString('N')
    $taskTemplate = if ($Game -eq 'gomoku') { 'sdk/gomoku/template.cpp' } else { 'sdk/template.cpp' }
    & $taskEnvironment tools\practice.py --game $Game --source $taskTemplate --maps 1 --players $Players --output $taskPreflight
    if ($LASTEXITCODE -ne 0) { throw 'Arena preflight failed. Resolve the environment before starting development.' }
    Write-Output ('Environment ready at ' + [DateTime]::UtcNow.ToString('o'))
    Write-Output ('Preflight report: ' + $taskPreflight + '/summary.md')
    $taskBrief = if (Test-Path -LiteralPath 'MODEL_TASK.md') { 'MODEL_TASK.md' } elseif ($Game -eq 'gomoku') { 'devkit/GOMOKU_MODEL_TASK.md' } else { 'devkit/MODEL_TASK.md' }
    Write-Output ('Now read ' + $taskBrief + ', and submit bot.cpp in this directory.')
} finally {
    Pop-Location
}
