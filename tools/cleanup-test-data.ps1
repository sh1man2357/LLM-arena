param([switch]$Apply, [switch]$IncludeGenerated, [switch]$ResetLocal, [switch]$OldDevkitsOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskPrefix = $taskRoot.TrimEnd('\') + '\'
$taskNames = @('artifacts\work', 'web\test-results', 'web\playwright-report')
if ($OldDevkitsOnly) {
    if ($IncludeGenerated -or $ResetLocal) { throw '-OldDevkitsOnly cannot be combined with broader cleanup options.' }
    $taskNames = @()
    $taskDistribution = [IO.Path]::GetFullPath((Join-Path $taskRoot 'artifacts\distribution'))
    if (Test-Path -LiteralPath $taskDistribution) {
        if ((Resolve-Path -LiteralPath $taskDistribution).Path -ne $taskDistribution -or
            ((Get-Item -LiteralPath $taskDistribution -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Unexpected distribution directory: $taskDistribution"
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $taskPackages = @()
        foreach ($taskZip in (Get-ChildItem -LiteralPath $taskDistribution -Filter 'llm-arena-*.zip' -File)) {
            if ($taskZip.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point: $($taskZip.FullName)" }
            $taskArchive = [IO.Compression.ZipFile]::OpenRead($taskZip.FullName)
            try {
                $taskManifestEntry = $taskArchive.GetEntry('devkit-manifest.json')
                if (-not $taskManifestEntry) { continue }
                $taskReader = [IO.StreamReader]::new($taskManifestEntry.Open())
                try { $taskManifest = $taskReader.ReadToEnd() | ConvertFrom-Json } finally { $taskReader.Dispose() }
                if ($taskManifest.format -ne 'llm-arena-public-devkit') { continue }
                $taskGame = if ($taskManifest.game_id) { $taskManifest.game_id } else { 'bomberman' }
                if ($taskGame -notin @('bomberman', 'gomoku')) { continue }
                $taskPackages += [PSCustomObject]@{ Game = $taskGame; File = $taskZip }
            } finally { $taskArchive.Dispose() }
        }
        foreach ($taskGroup in ($taskPackages | Group-Object Game)) {
            $taskOrdered = @($taskGroup.Group | Sort-Object @{ Expression = { $_.File.LastWriteTimeUtc }; Descending = $true }, @{ Expression = { $_.File.Name }; Descending = $true })
            $taskKeep = $taskOrdered[0].File
            $taskChecksum = [IO.Path]::ChangeExtension($taskKeep.FullName, '.sha256')
            if (-not (Test-Path -LiteralPath $taskChecksum -PathType Leaf)) { throw "Latest package checksum missing: $taskChecksum" }
            $taskExpectedHash = ((Get-Content -LiteralPath $taskChecksum -Raw).Trim() -split '\s+')[0]
            if ($taskExpectedHash -notmatch '^[a-fA-F0-9]{64}$' -or (Get-FileHash -LiteralPath $taskKeep.FullName -Algorithm SHA256).Hash -ne $taskExpectedHash) {
                throw "Latest package checksum mismatch: $($taskKeep.FullName)"
            }
            Write-Output "Keep $($taskGroup.Name): $($taskKeep.Name) and its SHA-256 file"
            foreach ($taskOld in ($taskOrdered | Select-Object -Skip 1)) {
                $taskNames += $taskOld.File.FullName.Substring($taskPrefix.Length)
                $taskOldChecksum = [IO.Path]::ChangeExtension($taskOld.File.FullName, '.sha256')
                if (Test-Path -LiteralPath $taskOldChecksum -PathType Leaf) { $taskNames += $taskOldChecksum.Substring($taskPrefix.Length) }
            }
        }
    }
}
if ($IncludeGenerated) {
    $taskNames += @('artifacts\acceptance', 'artifacts\distribution', 'web\dist')
    $taskNames += @(Get-ChildItem -LiteralPath (Join-Path $taskRoot 'web') -Filter '*.tsbuildinfo' -File -Force |
        ForEach-Object { $_.FullName.Substring($taskPrefix.Length) })
    foreach ($taskSource in @('engine', 'gomoku', 'replay', 'runner', 'runtime', 'service', 'tests', 'tools')) {
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
    if ($OldDevkitsOnly) {
        Write-Output 'Preview only. Use -OldDevkitsOnly -Apply to remove only older distribution packages and their checksum files; keep the newest per game by file modification time.'
    } else {
        Write-Output 'Preview only. Use -Apply after stopping test instances. -IncludeGenerated adds archives, distribution packages, frontend builds and source caches. -ResetLocal also deletes ALL default organizer data.'
    }
}
