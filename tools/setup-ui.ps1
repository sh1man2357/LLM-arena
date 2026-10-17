param(
    [string]$Python = '',
    [string]$NodeDirectory = '',
    [string]$CompilerArchive = '',
    [string]$WheelDirectory = ''
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskRuntime = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-lock.json') -Raw | ConvertFrom-Json
if ($NodeDirectory) {
    $taskNode = Join-Path $NodeDirectory 'node.exe'
    $taskNpm = Join-Path $NodeDirectory 'npm.cmd'
} else {
    $taskNodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $taskNodeCommand) { throw "Node.js $($taskRuntime.node) required. Install Node.js or pass -NodeDirectory." }
    $taskNode = $taskNodeCommand.Source
    $taskNpm = Join-Path (Split-Path -Parent $taskNode) 'npm.cmd'
}
if (-not (Test-Path -LiteralPath $taskNpm)) { throw 'npm.cmd is required alongside node.exe.' }
$taskNodeVersion = & $taskNode --version
$taskNpmVersion = & $taskNpm --version
if ($taskNodeVersion.Trim() -ne ('v' + $taskRuntime.node) -or $taskNpmVersion.Trim() -ne $taskRuntime.npm) {
    throw "Verified runtime required: Node $($taskRuntime.node), npm $($taskRuntime.npm)."
}
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
$Python = Resolve-ArenaPython -Python $Python
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskPipArguments = @('-m', 'pip', 'install', '--require-hashes', '-r', 'requirements.lock', '-r', 'requirements-service.lock')
if ($WheelDirectory) { $taskPipArguments += @('--no-index', '--find-links', (Resolve-Path -LiteralPath $WheelDirectory).Path) }
& $taskPython @taskPipArguments
if ($LASTEXITCODE -ne 0) { throw 'Locked Python dependencies installation failed.' }
if ($CompilerArchive) { & $taskPython tools\bootstrap.py --archive $CompilerArchive }
else { & $taskPython tools\bootstrap.py }
if ($LASTEXITCODE -ne 0) { throw 'Compiler setup failed.' }
$taskPriorPath = $env:PATH
try {
    $env:PATH = (Split-Path -Parent $taskNode) + ';' + $env:PATH
    Push-Location -LiteralPath (Join-Path $taskRoot 'web')
    try {
        & $taskNpm ci --cache (Join-Path $taskRoot '.tools\npm-cache') --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Locked frontend installation failed.' }
        & $taskNpm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
} finally { $env:PATH = $taskPriorPath }
Write-Output 'UI setup complete. Start with: powershell -ExecutionPolicy Bypass -File .\start-arena.ps1'
