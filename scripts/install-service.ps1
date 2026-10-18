# 注册 Windows 任务计划：用户登录时启动 mi-ai 保活总控
# 建议以当前用户身份运行；若权限不足可右键「以管理员身份运行」
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

$cfg = Get-MiAiServiceConfig
Ensure-MiAiLogDir -LogDir $cfg.LogDir

if (-not (Test-Path -LiteralPath $cfg.WatchdogScript)) {
    Write-Error "找不到 watchdog.ps1"
    exit 1
}
if (-not (Test-Path -LiteralPath $cfg.PythonExe)) {
    Write-Warning "尚未检测到 .venv，请确认已运行 scripts\install.ps1"
}
if (-not (Test-Path -LiteralPath (Join-Path $MiAiRoot ".env"))) {
    Write-Warning "尚未找到 .env，登录自启后可能因缺配置退出"
}

$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$($cfg.WatchdogScript)`""
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $arg `
    -WorkingDirectory $MiAiRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $MiAiTaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "小米音箱云端大模型桥接保活（mi-ai watchdog）" `
    -Force | Out-Null

Write-Host ("已注册任务计划：{0}" -f $MiAiTaskName)
Write-Host "触发：当前用户登录时"
Write-Host ("工作目录：{0}" -f $MiAiRoot)
Write-Host ("日志目录：{0}" -f $cfg.LogDir)
Write-Host ""
Write-Host "立即启动请运行：.\scripts\service-start.ps1"
Write-Host "查看状态请运行：.\scripts\service-status.ps1"
