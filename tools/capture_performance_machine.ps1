param(
    [string]$Output = 'artifacts/acceptance/v0.2-development/checks/performance-machine.json',
    [string]$Node = 'node.exe',
    [string]$Python = (Join-Path $PSScriptRoot '../.venv/Scripts/python.exe')
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOutput = [System.IO.Path]::GetFullPath((Join-Path $taskRoot $Output))
$taskProcessor = Get-CimInstance Win32_Processor
$taskOperatingSystem = Get-CimInstance Win32_OperatingSystem
$taskComputer = Get-CimInstance Win32_ComputerSystem
$taskNodeVersion = & $Node --version
if ($LASTEXITCODE -ne 0) { throw 'Node version read failed' }
$taskPythonVersion = & $Python --version
if ($LASTEXITCODE -ne 0) { throw 'Python version read failed' }
$taskMachine = [ordered]@{
    captured_at = (Get-Date).ToUniversalTime().ToString('o')
    cpu = @($taskProcessor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed)
    ram_bytes = $taskComputer.TotalPhysicalMemory
    os = ($taskOperatingSystem | Select-Object Caption,Version,BuildNumber)
    gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,CurrentRefreshRate)
    node = $taskNodeVersion
    python = $taskPythonVersion
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $taskOutput) | Out-Null
[System.IO.File]::WriteAllText($taskOutput, ($taskMachine | ConvertTo-Json -Depth 6), [System.Text.UTF8Encoding]::new($false))
Write-Output "Recorded machine configuration: $taskOutput"
