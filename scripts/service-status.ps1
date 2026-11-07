# 查看保活总控与各音箱进程状态
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

$cfg = Get-MiAiServiceConfig
Ensure-MiAiLogDir -LogDir $cfg.LogDir

Write-Host "=== mi-ai 服务状态 ==="
Write-Host ("项目目录：{0}" -f $MiAiRoot)
Write-Host ("日志目录：{0}" -f $cfg.LogDir)
Write-Host ("保活设备：{0}" -f ($cfg.Devices -join ", "))
if ($cfg.ConsoleEnabled) {
    Write-Host ("控制台：{0}" -f $cfg.ConsoleUrl)
}
else {
    Write-Host "控制台：已关闭（MI_AI_CONSOLE=0）"
}
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

if ($cfg.ConsoleEnabled) {
    $cpf = Join-Path $cfg.LogDir "console.pid"
    $cpid = Read-MiAiPidFile -Path $cpf
    $cproc = Get-MiAiProcessByPid -ProcessId $cpid
    $clog = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix "console"
    if ($cproc) {
        Write-Host ("console：运行中 wrapperPid={0} → {1}" -f $cpid, $cfg.ConsoleUrl)
    }
    else {
        Write-Host ("console：未运行（期望 {0}）" -f $cfg.ConsoleUrl)
    }
    Write-Host ("  今日日志：{0}" -f $clog)
}

$wlog = Get-MiAiDailyLogPath -LogDir $cfg.LogDir -Prefix "watchdog"
Write-Host ("watchdog 今日日志：{0}" -f $wlog)

$authReq = Join-Path $cfg.LogDir "AUTH_REQUIRED.txt"
$tokenPath = Join-Path $MiAiRoot "data\mi.token"
$seedPath = Join-Path $MiAiRoot "data\mi_pass_seed.json"
Write-Host ("token 文件：{0}（{1}）" -f $tokenPath, $(if (Test-Path $tokenPath) { "存在" } else { "缺失" }))
Write-Host ("passToken 种子：{0}（{1}）" -f $seedPath, $(if (Test-Path $seedPath) { "存在" } else { "缺失" }))
if (Test-Path -LiteralPath $authReq) {
    Write-Host "鉴权告警：需要人工验证 → logs\AUTH_REQUIRED.txt"
    Get-Content -LiteralPath $authReq -TotalCount 8 -ErrorAction SilentlyContinue
}
else {
    Write-Host "鉴权告警：无"
}
