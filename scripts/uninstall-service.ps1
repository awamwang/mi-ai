# 注销任务计划，并默认先停止正在运行的服务
param(
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

if (-not $KeepRunning) {
    & (Join-Path $PSScriptRoot "service-stop.ps1")
}

$task = Get-ScheduledTask -TaskName $MiAiTaskName -ErrorAction SilentlyContinue
if ($task) {
    Unregister-ScheduledTask -TaskName $MiAiTaskName -Confirm:$false
    Write-Host ("已注销任务计划：{0}" -f $MiAiTaskName)
}
else {
    Write-Host ("任务计划不存在：{0}" -f $MiAiTaskName)
}
