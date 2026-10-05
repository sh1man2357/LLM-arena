param([string]$Python = '', [string]$CompilerArchive = '', [string]$WheelDirectory = '')
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $taskEnvironment = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $taskReady = $false
    if (Test-Path -LiteralPath $taskEnvironment) {
        & $taskEnvironment tools\devkit_ready.py
        $taskReady = $LASTEXITCODE -eq 0
    }
    if (-not $taskReady) {
        & (Join-Path $PSScriptRoot 'tools\setup.ps1') -Python $Python -CompilerArchive $CompilerArchive -WheelDirectory $WheelDirectory
    }
    $taskPreflight = 'artifacts/work/preflight-' + [guid]::NewGuid().ToString('N')
    & $taskEnvironment tools\practice.py --source sdk/template.cpp --maps 1 --output $taskPreflight
    if ($LASTEXITCODE -ne 0) { throw 'Arena preflight failed. Resolve the environment before starting development.' }
    Write-Output ('Environment ready at ' + [DateTime]::UtcNow.ToString('o'))
    Write-Output ('Preflight report: ' + $taskPreflight + '/summary.md')
    Write-Output 'Now record your 60-minute deadline, read MODEL_TASK.md, and submit bot.cpp in this directory.'
} finally {
    Pop-Location
}
