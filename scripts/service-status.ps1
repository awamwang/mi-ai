# 查看保活总控与各音箱进程状态
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

$cfg = Get-MiAiServiceConfig
Ensure-MiAiLogDir -LogDir $cfg.LogDir

Write-Host "=== mi-ai 服务状态 ==="
Write-Host ("项目目录：{0}" -f $MiAiRoot)
Write-Host ("日志目录：{0}" -f $cfg.LogDir)
Write-Host ("保活设备：{0}" -f ($cfg.Devices -join ", "))
Write-Host ("任务计划：{0}" -f $MiAiTaskName)

$task = Get-ScheduledTask -TaskName $MiAiTaskName -ErrorAction SilentlyContinue
if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $MiAiTaskName -ErrorAction SilentlyContinue
    Write-Host ("任务状态：{0}（上次结果={1}）" -f $task.State, $(if ($info) { $info.LastTaskResult } else { "n/a" }))
}
else {
    Write-Host "任务状态：未安装（可运行 scripts\install-service.ps1）"
}

$wd = Test-MiAiWatchdogRunning
if ($wd.Running) {
    Write-Host ("watchdog：运行中 pid={0}" -f $wd.Pid)
}
else {
    Write-Host "watchdog：未运行"
}

foreach ($device in $cfg.Devices) {
    $pf = Join-Path $cfg.LogDir ("{0}.pid" -f $device)
    $dpid = Read-MiAiPidFile -Path $pf
    $proc = Get-MiAiProcessByPid -ProcessId $dpid
    $log = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix $device
    if ($proc) {
        Write-Host ("{0}：运行中 wrapperPid={1}" -f $device, $dpid)
    }
    else {
        Write-Host ("{0}：未运行" -f $device)
    }
    Write-Host ("  今日日志：{0}" -f $log)
}

$wlog = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix "watchdog"
Write-Host ("watchdog 今日日志：{0}" -f $wlog)
