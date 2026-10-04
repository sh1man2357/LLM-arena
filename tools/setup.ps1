param([string]$Python = '', [string]$CompilerArchive = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not $Python) {
    $taskCandidates = @(
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    $taskPythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($taskPythonCommand) { $taskCandidates += $taskPythonCommand.Source }
    foreach ($taskCandidate in $taskCandidates) {
        if (Test-Path -LiteralPath $taskCandidate) { $Python = $taskCandidate; break }
    }
}
if (-not $Python) { throw 'Python 3.12 required: pass -Python with its executable path.' }
& $Python -c 'import sys; assert sys.version_info[:2] == (3,12), "Python 3.12 required"'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
& '.\.venv\Scripts\python.exe' -m pip install --require-hashes -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Locked dependencies installation failed.' }
if ($CompilerArchive) {
    & '.\.venv\Scripts\python.exe' tools\bootstrap.py --archive $CompilerArchive
} else {
    & '.\.venv\Scripts\python.exe' tools\bootstrap.py
}
if ($LASTEXITCODE -ne 0) { throw 'Compiler setup failed.' }
Write-Output 'Setup complete. Run .\.venv\Scripts\python.exe arena.py --help'
