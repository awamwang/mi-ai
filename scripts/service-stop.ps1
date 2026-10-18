# 停止保活总控及其子进程
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

$cfg = Get-MiAiServiceConfig
Ensure-MiAiLogDir -LogDir $cfg.LogDir

$watchPidFile = Join-Path $cfg.LogDir "watchdog.pid"
$wid = Read-MiAiPidFile -Path $watchPidFile

# 先停总控，避免清理子进程后又被拉起
if ($wid -gt 0) {
    Write-Host ("停止 watchdog pid={0}" -f $wid)
    Stop-MiAiProcessTree -ProcessId $wid
    Remove-Item -LiteralPath $watchPidFile -Force -ErrorAction SilentlyContinue
}
else {
    Write-Host "未找到 watchdog.pid，继续清理设备进程…"
}

Get-ChildItem -LiteralPath $cfg.LogDir -Filter "*.pid" -ErrorAction SilentlyContinue |
    ForEach-Object {
        if ($_.Name -eq "watchdog.pid") {
            return
        }
        $childPid = Read-MiAiPidFile -Path $_.FullName
        if ($childPid -gt 0) {
            Write-Host ("停止设备进程树 pid={0} ({1})" -f $childPid, $_.Name)
            Stop-MiAiProcessTree -ProcessId $childPid
        }
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
    }

# 兜底：仅清理本项目脚本拉起的残留进程
$rootHint = $MiAiRoot.Replace("'", "''")
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and (
            ($_.CommandLine -like "*$rootHint*run-device.ps1*") -or
            ($_.CommandLine -like "*$rootHint*watchdog.ps1*") -or
            ($_.CommandLine -like "*$rootHint*.venv\Scripts\python.exe*-m mi_ai run*")
        )
    } |
    ForEach-Object {
        Write-Host ("清理残留进程 pid={0}" -f $_.ProcessId)
        Stop-MiAiProcessTree -ProcessId $_.ProcessId
    }

Write-Host "mi-ai 已停止"
