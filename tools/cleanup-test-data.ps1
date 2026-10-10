param([switch]$Apply, [switch]$IncludeGenerated, [switch]$ResetLocal)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskPrefix = $taskRoot.TrimEnd('\') + '\'
$taskNames = @('artifacts\work', 'web\test-results', 'web\playwright-report')
if ($IncludeGenerated) {
    $taskNames += @('artifacts\acceptance', 'artifacts\distribution', 'web\dist')
    $taskNames += @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'web') -Filter '*.tsbuildinfo' -File -Force |
        ForEach-Object { $_.FullName.Substring($taskPrefix.Length) })
    foreach ($taskSource in @('engine', 'replay', 'runner', 'runtime', 'service', 'tests', 'tools')) {
        $taskSourcePath = Join-Path $taskRoot $taskSource
        $taskCachePath = Join-Path $taskSourcePath '__pycache__'
        if (Test-Path -LiteralPath $taskCachePath) { $taskNames += "$taskSource\__pycache__" }
    }
}
if ($ResetLocal) { $taskNames += 'artifacts\local' }
$taskTargets = @()
$taskBytes = 0L
$taskFiles = 0L

# Validate every target before deleting anything. Runtime data is opt-in because
# a real organizer's submissions may use the default local workspace.
foreach ($taskName in $taskNames) {
    $taskExpected = [IO.Path]::GetFullPath((Join-Path $taskRoot $taskName))
    if (-not $taskExpected.StartsWith($taskPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escapes project: $taskExpected"
    }
    if (-not (Test-Path -LiteralPath $taskExpected)) { continue }
    $taskTarget = (Resolve-Path -LiteralPath $taskExpected).Path
    if ($taskTarget -ne $taskExpected) { throw "Unexpected resolved path: $taskTarget" }
    $taskItem = Get-Item -LiteralPath $taskTarget -Force
    if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Reparse points prevent cleanup: $taskTarget"
    }
    $taskTracked = @(& git -C $taskRoot ls-files -- $taskName.Replace('\', '/'))
    if ($LASTEXITCODE -ne 0) { throw 'Unable to check tracked files.' }
    if ($taskTracked.Count) { throw "Tracked files prevent cleanup: $taskTarget" }
    $taskEntries = if ($taskItem.PSIsContainer) { @(Get-ChildItem -LiteralPath $taskTarget -Recurse -Force) } else { @($taskItem) }
    if (@($taskEntries | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw "Reparse points prevent recursive cleanup: $taskTarget"
    }
    foreach ($taskLock in ($taskEntries | Where-Object { $_.Name -eq 'worker.lock' -and -not $_.PSIsContainer })) {
        $taskHandle = $null
        try {
            $taskHandle = [IO.File]::Open($taskLock.FullName, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        } catch {
            throw "Stop the service using this workspace before cleaning: $($taskLock.DirectoryName)"
        } finally {
            if ($taskHandle) { $taskHandle.Dispose() }
        }
    }
    $taskSize = 0L
    $taskCount = 0L
    foreach ($taskFile in ($taskEntries | Where-Object { -not $_.PSIsContainer })) {
        $taskSize += $taskFile.Length
        $taskCount++
    }
    $taskTargets += $taskTarget
    $taskBytes += $taskSize
    $taskFiles += $taskCount
    Write-Output ('{0}: {1:N3} GiB, {2} files' -f $taskName, ($taskSize / 1GB), $taskCount)
}

if ($Apply) {
    foreach ($taskTarget in $taskTargets) {
        # Resolved absolute paths above are confined to the named project roots.
        Remove-Item -LiteralPath $taskTarget -Recurse -Force
        if (Test-Path -LiteralPath $taskTarget) { throw "Cleanup incomplete: $taskTarget" }
    }
    Write-Output ('Removed {0} targets and {1} files; freed {2:N3} GiB.' -f $taskTargets.Count, $taskFiles, ($taskBytes / 1GB))
} else {
    Write-Output 'Preview only. Use -Apply after stopping test instances. -IncludeGenerated adds archives, distribution packages, frontend builds and source caches. -ResetLocal also deletes ALL default organizer data.'
}
