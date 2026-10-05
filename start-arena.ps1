param([int]$Port = 8787, [string]$Data = '', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be between 1024 and 65535.' }
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython) -or -not (Test-Path -LiteralPath (Join-Path $taskRoot 'web\dist\index.html'))) {
    & (Join-Path $taskRoot 'tools\setup-ui.ps1')
}
& $taskPython -c 'import fastapi, uvicorn, wasmtime'
if ($LASTEXITCODE -ne 0) { throw 'Service dependencies missing. Run tools\setup-ui.ps1 first.' }
if (-not $Data) { $Data = Join-Path $taskRoot 'artifacts\local' }
$taskData = [IO.Path]::GetFullPath($Data)
New-Item -ItemType Directory -Force -Path $taskData | Out-Null
$taskSocket = [Net.Sockets.TcpClient]::new()
try { $taskSocket.Connect('127.0.0.1', $Port); $taskBusy = $true } catch { $taskBusy = $false } finally { $taskSocket.Dispose() }
if ($taskBusy) { throw "Port $Port is already in use. Stop that instance or select another -Port." }
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskLog = Join-Path $taskData "server-$taskStamp.log"
$taskErrorLog = Join-Path $taskData "server-$taskStamp-error.log"
$taskArguments = @('-m', 'service', '--demo', '--port', "$Port", '--data', ('"' + $taskData + '"'))
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $taskLog -RedirectStandardError $taskErrorLog
try {
    $taskUrl = "http://127.0.0.1:$Port"
    $taskReady = $false
    for ($taskTry = 0; $taskTry -lt 60; $taskTry++) {
        if ($taskProcess.HasExited) { throw "Server stopped. Read $taskErrorLog" }
        try { $taskHealth = Invoke-RestMethod "$taskUrl/health" -TimeoutSec 1; $taskReady = $taskHealth.status -eq 'ready' } catch { }
        if ($taskReady) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $taskReady) { throw "Server did not become ready. Read $taskErrorLog" }
    Write-Output "LLM Arena: $taskUrl"
    Write-Output "Data: $taskData"
    Write-Output "Log: $taskErrorLog"
    if (-not $NoBrowser) { Start-Process $taskUrl }
    Read-Host 'Press Enter to stop this local instance' | Out-Null
} finally {
    if (-not $taskProcess.HasExited) {
        & taskkill.exe /PID $taskProcess.Id /T /F | Out-Null
        $taskProcess.WaitForExit()
    }
}
