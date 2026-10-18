# 立即启动保活总控（若已在运行则直接提示）
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_service-common.ps1")

$cfg = Get-MiAiServiceConfig
Ensure-MiAiLogDir -LogDir $cfg.LogDir

$existing = Test-MiAiWatchdogRunning
if ($existing.Running) {
    Write-Host ("mi-ai 已在运行（watchdog pid={0}）" -f $existing.Pid)
    exit 0
}

if (-not (Test-Path -LiteralPath $cfg.PythonExe)) {
    Write-Error "找不到 .venv\Scripts\python.exe，请先运行 scripts\install.ps1"
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $MiAiRoot ".env"))) {
    Write-Error "缺少 .env，请先复制 .env.example 并填写配置"
    exit 1
}

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoProfile"
        "-ExecutionPolicy", "Bypass"
        "-WindowStyle", "Hidden"
        "-File", $cfg.WatchdogScript
    ) `
    -WorkingDirectory $MiAiRoot `
    -WindowStyle Hidden `
    -PassThru

# 稍等 PID 文件落地
$ok = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 200
    $state = Test-MiAiWatchdogRunning
    if ($state.Running) {
        Write-Host ("已启动 mi-ai watchdog pid={0}（启动器 pid={1}）" -f $state.Pid, $proc.Id)
        Write-Host ("日志目录：{0}" -f $cfg.LogDir)
        $ok = $true
        break
    }
}

if (-not $ok) {
    Write-Warning "已发起启动，但尚未检测到 watchdog.pid。请查看 logs\watchdog-*.log"
    exit 1
}
