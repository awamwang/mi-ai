# 由 watchdog 拉起：运行本机控制台并将输出追加到当日日志
param(
    [Parameter(Mandatory)][string]$LogPath,
    [Parameter(Mandatory)][string]$Root,
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 18865
)

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $Root

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$logDir = Split-Path -Parent $LogPath
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
    $msg = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') 错误：找不到 Python：$py"
    Add-Content -LiteralPath $LogPath -Value $msg -Encoding UTF8
    exit 1
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -LiteralPath $LogPath -Value (
    "$stamp ===== 启动 console http://${HostAddress}:${Port}/ ====="
) -Encoding UTF8

& $py -m mi_ai.console --host $HostAddress --port $Port --no-open 2>&1 | ForEach-Object {
    $line = "$_"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}
$code = $LASTEXITCODE
if ($null -eq $code) {
    $code = 0
}

$stamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -LiteralPath $LogPath -Value "$stamp2 ===== 退出 console code=$code =====" -Encoding UTF8
exit $code
