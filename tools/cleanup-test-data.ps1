param([switch]$Apply, [switch]$ResetLocal)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskPrefix = $taskRoot.TrimEnd('\') + '\'
$taskNames = @('artifacts\work', 'web\test-results', 'web\playwright-report')
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
    if (-not $taskItem.PSIsContainer -or ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Expected a normal directory: $taskTarget"
    }
    $taskTracked = @(& git -C $taskRoot ls-files -- $taskName.Replace('\', '/'))
    if ($LASTEXITCODE -ne 0) { throw 'Unable to check tracked files.' }
    if ($taskTracked.Count) { throw "Tracked files prevent cleanup: $taskTarget" }
    $taskEntries = @(Get-ChildItem -LiteralPath $taskTarget -Recurse -Force)
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
    Write-Output ('Removed {0} directories and {1} files; freed {2:N3} GiB.' -f $taskTargets.Count, $taskFiles, ($taskBytes / 1GB))
} else {
    Write-Output 'Preview only. Use -Apply after stopping test instances. -ResetLocal also deletes ALL default organizer data.'
}
