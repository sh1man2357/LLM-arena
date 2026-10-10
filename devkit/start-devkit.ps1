param([string]$Python = '', [string]$CompilerArchive = '', [string]$WheelDirectory = '')
$ErrorActionPreference = 'Stop'
$taskRoot = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'arena.py')) { $PSScriptRoot } else { Split-Path -Parent $PSScriptRoot }
Push-Location -LiteralPath $taskRoot
try {
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
    & $taskEnvironment tools\practice.py --source sdk/template.cpp --maps 1 --output $taskPreflight
    if ($LASTEXITCODE -ne 0) { throw 'Arena preflight failed. Resolve the environment before starting development.' }
    Write-Output ('Environment ready at ' + [DateTime]::UtcNow.ToString('o'))
    Write-Output ('Preflight report: ' + $taskPreflight + '/summary.md')
    $taskBrief = if (Test-Path -LiteralPath 'MODEL_TASK.md') { 'MODEL_TASK.md' } else { 'devkit/MODEL_TASK.md' }
    Write-Output ('Now read ' + $taskBrief + ', and submit bot.cpp in this directory.')
} finally {
    Pop-Location
}
