# mi-ai 保活总控：按配置拉起音箱进程，异常退出后带退避重启
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

$cfg = Get-MiAiServiceConfig
Ensure-MiAiLogDir -LogDir $cfg.LogDir
Clear-MiAiOldLogs -LogDir $cfg.LogDir -KeepDays $cfg.LogKeepDays

$watchLog = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix "watchdog"
$pidFile = Join-Path $cfg.LogDir "watchdog.pid"

# 防止重复启动
$existing = Test-MiAiWatchdogRunning
if ($existing.Running -and $existing.Pid -ne $PID) {
    Write-MiAiLog -LogPath $watchLog -Message ("已有 watchdog 在运行 pid={0}，本实例退出" -f $existing.Pid)
    exit 0
}

if (-not (Test-Path -LiteralPath $cfg.PythonExe)) {
    Write-MiAiLog -LogPath $watchLog -Message ("致命：找不到虚拟环境 Python：{0}" -f $cfg.PythonExe)
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $MiAiRoot ".env"))) {
    Write-MiAiLog -LogPath $watchLog -Message "致命：缺少 .env，请先配置后重试"
    exit 1
}
if (-not (Test-Path -LiteralPath $cfg.RunDeviceScript)) {
    Write-MiAiLog -LogPath $watchLog -Message ("致命：缺少 {0}" -f $cfg.RunDeviceScript)
    exit 1
}

Write-MiAiPidFile -Path $pidFile -ProcessId $PID
Write-MiAiLog -LogPath $watchLog -Message (
    "watchdog 启动 pid={0} devices={1} base={2}s max={3}s log={4}" -f `
        $PID, ($cfg.Devices -join ","), $cfg.RestartBaseSec, $cfg.RestartMaxSec, $cfg.LogDir
)

# 每台设备的运行状态
$states = @{}
foreach ($device in $cfg.Devices) {
    $states[$device] = [pscustomobject]@{
        Device     = $device
        Process    = $null
        FailCount  = 0
        StartedAt  = $null
        NextStart  = Get-Date
        DevicePidFile = Join-Path $cfg.LogDir ("{0}.pid" -f $device)
    }
}

function Stop-AllChildren {
    foreach ($device in @($states.Keys)) {
        $st = $states[$device]
        if ($st.Process -and -not $st.Process.HasExited) {
            Stop-MiAiProcessTree -ProcessId $st.Process.Id
        }
        if (Test-Path -LiteralPath $st.DevicePidFile) {
            Remove-Item -LiteralPath $st.DevicePidFile -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    $lastCleanupDay = (Get-Date).Date

    while ($true) {
        $now = Get-Date
        if ($now.Date -ne $lastCleanupDay) {
            Clear-MiAiOldLogs -LogDir $cfg.LogDir -KeepDays $cfg.LogKeepDays
            $lastCleanupDay = $now.Date
            $watchLog = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix "watchdog"
            Write-MiAiLog -LogPath $watchLog -Message "日期变更，已执行日志清理"
        }

        foreach ($device in $cfg.Devices) {
            $st = $states[$device]

            if ($st.Process -and -not $st.Process.HasExited) {
                continue
            }

            # 子进程刚退出：记账并计算退避
            if ($st.Process -and $st.Process.HasExited) {
                $lived = 0
                if ($st.StartedAt) {
                    try {
                        $lived = ($st.Process.ExitTime - $st.StartedAt).TotalSeconds
                    }
                    catch {
                        $lived = ((Get-Date) - $st.StartedAt).TotalSeconds
                    }
                    if ($lived -lt 0) {
                        $lived = ((Get-Date) - $st.StartedAt).TotalSeconds
                    }
                }
                $exitCode = -1
                try {
                    $exitCode = $st.Process.ExitCode
                }
                catch {
                    $exitCode = -1
                }
                if ($lived -ge $MiAiStableSeconds) {
                    $st.FailCount = 0
                    $st.NextStart = Get-Date
                    Write-MiAiLog -LogPath $watchLog -Message (
                        "{0} 退出 code={1} 已稳定运行 {2:N0}s，重置退避" -f $device, $exitCode, $lived
                    )
                }
                else {
                    $st.FailCount = $st.FailCount + 1
                    $delay = Get-MiAiBackoffSeconds -FailCount $st.FailCount -BaseSec $cfg.RestartBaseSec -MaxSec $cfg.RestartMaxSec
                    $st.NextStart = (Get-Date).AddSeconds($delay)
                    Write-MiAiLog -LogPath $watchLog -Message (
                        "{0} 异常退出 code={1} lived={2:N0}s fail#{3}，{4}s 后重启" -f `
                            $device, $exitCode, $lived, $st.FailCount, $delay
                    )
                }
                $st.Process = $null
                if (Test-Path -LiteralPath $st.DevicePidFile) {
                    Remove-Item -LiteralPath $st.DevicePidFile -Force -ErrorAction SilentlyContinue
                }
            }

            if ((Get-Date) -lt $st.NextStart) {
                continue
            }

            $deviceLog = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix $device
            $argList = @(
                "-NoProfile"
                "-ExecutionPolicy", "Bypass"
                "-File", $cfg.RunDeviceScript
                "-Device", $device
                "-LogPath", $deviceLog
                "-Root", $MiAiRoot
            )
            try {
                $proc = Start-Process -FilePath "powershell.exe" `
                    -ArgumentList $argList `
                    -WorkingDirectory $MiAiRoot `
                    -WindowStyle Hidden `
                    -PassThru
                $st.Process = $proc
                $st.StartedAt = Get-Date
                Write-MiAiPidFile -Path $st.DevicePidFile -ProcessId $proc.Id
                Write-MiAiLog -LogPath $watchLog -Message (
                    "已启动 {0} wrapperPid={1} log={2}" -f $device, $proc.Id, $deviceLog
                )
            }
            catch {
                $st.FailCount = $st.FailCount + 1
                $delay = Get-MiAiBackoffSeconds -FailCount $st.FailCount -BaseSec $cfg.RestartBaseSec -MaxSec $cfg.RestartMaxSec
                $st.NextStart = (Get-Date).AddSeconds($delay)
                Write-MiAiLog -LogPath $watchLog -Message (
                    "启动 {0} 失败：{1}；{2}s 后重试" -f $device, $_.Exception.Message, $delay
                )
            }
        }

        Start-Sleep -Seconds 2
    }
}
finally {
    Write-MiAiLog -LogPath $watchLog -Message "watchdog 正在退出，清理子进程"
    Stop-AllChildren
    if (Test-Path -LiteralPath $pidFile) {
        $cur = Read-MiAiPidFile -Path $pidFile
        if ($cur -eq $PID) {
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        }
    }
}
