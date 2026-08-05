$global:repoPath = "C:\Users\여분\Downloads\업무효율화"
$global:logFile = Join-Path $repoPath "auto-sync.log"
Set-Location $repoPath

function Write-Log($msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File -FilePath $global:logFile -Append -Encoding utf8
}

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $repoPath
$watcher.IncludeSubdirectories = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, LastWrite, Size, DirectoryName'
$watcher.EnableRaisingEvents = $true

$global:timer = New-Object System.Timers.Timer
$timer.Interval = 5000
$timer.AutoReset = $false

$syncAction = {
    try {
        Set-Location $global:repoPath
        $status = git status --porcelain 2>$null
        if ($status) {
            git add -A 2>&1 | Out-Null
            $msg = "Auto sync: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
            git commit -m $msg 2>&1 | Out-Null
            git fetch origin 2>&1 | Out-Null
            git rebase origin/main 2>&1 | Out-Null
            $pushResult = git push origin main 2>&1 | Out-String
            Write-Log "Synced. push output: $pushResult"
        }
    } catch {
        Write-Log "ERROR: $_"
    }
}

$onChange = {
    try {
        $path = $Event.SourceEventArgs.FullPath
        if ($path.IndexOf('\.git\', [StringComparison]::OrdinalIgnoreCase) -ge 0) { return }
        if ($path -like "*auto-sync.log*" -or $path -like "*stderr.log*" -or $path -like "*stdout.log*") { return }
        $global:timer.Stop()
        $global:timer.Start()
    } catch {
        Write-Log "ERROR in onChange: $_"
    }
}

Register-ObjectEvent $watcher Changed -Action $onChange | Out-Null
Register-ObjectEvent $watcher Created -Action $onChange | Out-Null
Register-ObjectEvent $watcher Deleted -Action $onChange | Out-Null
Register-ObjectEvent $watcher Renamed -Action $onChange | Out-Null
Register-ObjectEvent $timer Elapsed -Action $syncAction | Out-Null

Write-Log "Watcher started."
while ($true) { Wait-Event -Timeout 2 | Out-Null }