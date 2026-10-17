function Resolve-ArenaPython {
    param([string]$Python = '')
    $taskCandidates = @()
    if ($Python) {
        if (Test-Path -LiteralPath $Python -PathType Leaf) { $taskCandidates += (Resolve-Path -LiteralPath $Python).Path }
        else {
            $taskCommand = Get-Command $Python -ErrorAction SilentlyContinue
            if ($taskCommand) { $taskCandidates += $taskCommand.Source }
        }
    } else {
        $taskCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($taskCommand) { $taskCandidates += $taskCommand.Source }
        $taskLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($taskLauncher) {
            try {
                $taskLaunched = & $taskLauncher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0 -and $taskLaunched) { $taskCandidates += $taskLaunched }
            } catch { }
        }
        $taskCandidates += @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
            'C:\Python312\python.exe',
            (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
        )
    }
    foreach ($taskCandidate in ($taskCandidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $taskCandidate -PathType Leaf)) { continue }
        try {
            & $taskCandidate -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $taskCandidate }
        } catch { }
    }
    throw 'Python 3.12 required. Install it from python.org, or pass -Python with its executable path.'
}
