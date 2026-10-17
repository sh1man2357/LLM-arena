param([int]$Port = 8798, [string]$Data = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if ($Port -lt 1024 -or $Port -gt 65535 -or $Port -eq 8787) { throw 'Choose a dedicated test port (1024..65535, except 8787).' }
$taskWork = [IO.Path]::GetFullPath((Join-Path $taskRoot 'artifacts\work')) + [IO.Path]::DirectorySeparatorChar
if (-not $Data) { $Data = Join-Path $taskWork ('browser-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)) }
$taskData = [IO.Path]::GetFullPath($Data)
if (-not $taskData.StartsWith($taskWork, [StringComparison]::OrdinalIgnoreCase)) { throw 'Browser test data must be under artifacts/work.' }
if (Test-Path -LiteralPath $taskData) { throw 'Use a new test data directory; existing data is preserved.' }
$taskSocket = [Net.Sockets.TcpClient]::new()
try { $taskSocket.Connect('127.0.0.1', $Port); $taskBusy = $true } catch { $taskBusy = $false } finally { $taskSocket.Dispose() }
if ($taskBusy) { throw "Test port $Port is already in use." }
New-Item -ItemType Directory -Path $taskData -Force | Out-Null
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskPriorUrl = $env:ARENA_BASE_URL
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-m', 'service', '--demo', '--port', "$Port", '--data', ('"' + $taskData + '"')) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskData 'server.log') -RedirectStandardError (Join-Path $taskData 'server-error.log')
try {
    $taskUrl = "http://127.0.0.1:$Port"
    $taskReady = $false
    for ($taskTry = 0; $taskTry -lt 60; $taskTry++) {
        if ($taskProcess.HasExited) { throw "Test server exited. Read $taskData\server-error.log" }
        try { $taskReady = (Invoke-RestMethod "$taskUrl/health" -TimeoutSec 1).status -eq 'ready' } catch { }
        if ($taskReady) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $taskReady) { throw 'Test server did not become ready.' }
    $env:ARENA_BASE_URL = $taskUrl
    Push-Location -LiteralPath (Join-Path $taskRoot 'web')
    try {
        & npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw "Browser tests failed. Logs retained at $taskData" }
    } finally { Pop-Location }
} finally {
    $env:ARENA_BASE_URL = $taskPriorUrl
    if (-not $taskProcess.HasExited) { & taskkill.exe /PID $taskProcess.Id /T /F | Out-Null; $taskProcess.WaitForExit() }
}
