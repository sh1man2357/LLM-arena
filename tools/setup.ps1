param([string]$Python = '', [string]$CompilerArchive = '', [string]$WheelDirectory = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
. (Join-Path $PSScriptRoot 'python-runtime.ps1')
$Python = Resolve-ArenaPython -Python $Python
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
$taskPipOptions = @()
if ($WheelDirectory) { $taskPipOptions = @('--no-index', '--find-links', $WheelDirectory) }
& '.\.venv\Scripts\python.exe' -m pip install --require-hashes -r requirements.lock @taskPipOptions
if ($LASTEXITCODE -ne 0) { throw 'Locked dependencies installation failed.' }
if ($CompilerArchive) {
    & '.\.venv\Scripts\python.exe' tools\bootstrap.py --archive $CompilerArchive
} else {
    & '.\.venv\Scripts\python.exe' tools\bootstrap.py
}
if ($LASTEXITCODE -ne 0) { throw 'Compiler setup failed.' }
Write-Output 'Setup complete. Run .\.venv\Scripts\python.exe arena.py --help'
