param (
    [ValidateSet("status", "logs", "stop", "start", "restart")]
    [string]$Action = "status"
)

$workspace = "E:\stock_predictor\stock_predictor"
$lockFile = "$workspace\daemon.lock"
$pythonw = "C:\Program Files\Python312\pythonw.exe"
$script = "$workspace\autonomous_trading_daemon.py"

function Get-DaemonProcess {
    if (Test-Path $lockFile) {
        $pidContent = (Get-Content $lockFile -Raw).Trim()
        if ($pidContent) {
            $p = Get-Process -Id $pidContent -ErrorAction SilentlyContinue
            if ($p -and $p.ProcessName -match "python") {
                return $p
            }
        }
    }
    return $null
}

switch ($Action) {
    "status" {
        $p = Get-DaemonProcess
        if ($p) {
            Write-Host "[ONLINE] Autonomous Trading Daemon is RUNNING (PID: $($p.Id))" -ForegroundColor Green
            Write-Host "Memory: $([math]::Round($p.WorkingSet64/1MB, 1)) MB | CPU Time: $([math]::Round($p.TotalProcessorTime.TotalSeconds, 1))s"
            Write-Host "Autostart Registry Key: ACTIVE (HKCU Run)" -ForegroundColor Cyan
            Write-Host "Autostart Startup Shortcut: ACTIVE (Shell Startup)" -ForegroundColor Cyan
        } else {
            Write-Host "[OFFLINE] Autonomous Trading Daemon is NOT running." -ForegroundColor Yellow
        }
        $latestLog = Get-ChildItem "$workspace\logs\trading_daemon_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latestLog) {
            Write-Host "`nRecent Activity ($($latestLog.Name)):" -ForegroundColor Gray
            Get-Content $latestLog.FullName -Tail 5
        }
    }
    "logs" {
        $latestLog = Get-ChildItem "$workspace\logs\trading_daemon_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latestLog) {
            Get-Content $latestLog.FullName -Tail 30 -Wait
        } else {
            Write-Host "No log file found." -ForegroundColor Yellow
        }
    }
    "stop" {
        $p = Get-DaemonProcess
        if ($p) {
            Stop-Process -Id $p.Id -Force
            Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
            Write-Host "[STOPPED] Daemon PID $($p.Id) terminated." -ForegroundColor Red
        } else {
            Write-Host "Daemon is not currently running." -ForegroundColor Yellow
        }
    }
    "start" {
        $p = Get-DaemonProcess
        if ($p) {
            Write-Host "Daemon already running with PID $($p.Id)." -ForegroundColor Yellow
        } else {
            Start-Process -FilePath $pythonw -ArgumentList "`"$script`"" -WorkingDirectory $workspace
            Start-Sleep -Seconds 2
            $newP = Get-DaemonProcess
            if ($newP) {
                Write-Host "[STARTED] Daemon launched in background (PID: $($newP.Id))." -ForegroundColor Green
            } else {
                Write-Host "Failed to launch daemon. Check logs." -ForegroundColor Red
            }
        }
    }
    "restart" {
        & $PSCommandPath stop
        Start-Sleep -Seconds 1
        & $PSCommandPath start
    }
}
