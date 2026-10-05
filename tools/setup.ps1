param([string]$Python = '', [string]$CompilerArchive = '', [string]$WheelDirectory = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not $Python) {
    $taskCandidates = @(
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
    )
    $taskPythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($taskPythonCommand) { $taskCandidates += $taskPythonCommand.Source }
    $taskPythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($taskPythonLauncher) {
        try {
            $taskLaunchedPython = & $taskPythonLauncher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $taskLaunchedPython) { $taskCandidates += $taskLaunchedPython }
        } catch { } # A launcher without Python 3.12 is not a usable candidate.
    }
    $taskCandidates += @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        'C:\Python312\python.exe'
    )
    foreach ($taskCandidate in $taskCandidates) {
        if (Test-Path -LiteralPath $taskCandidate) {
            & $taskCandidate -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $Python = $taskCandidate; break }
        }
    }
}
if (-not $Python) { throw 'Python 3.12 required: pass -Python with its executable path.' }
& $Python -c "import sys; assert sys.version_info[:2] == (3,12), 'Python 3.12 required'"
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
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
