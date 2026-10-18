# 由 watchdog 拉起：运行指定音箱并将输出追加到当日日志
param(
    [Parameter(Mandatory)][string]$Device,
    [Parameter(Mandatory)][string]$LogPath,
    [Parameter(Mandatory)][string]$Root
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
Add-Content -LiteralPath $LogPath -Value "$stamp ===== 启动 $Device =====" -Encoding UTF8

& $py -m mi_ai run $Device *>> $LogPath
$code = $LASTEXITCODE
if ($null -eq $code) {
    $code = 0
}

$stamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -LiteralPath $LogPath -Value "$stamp2 ===== 退出 $Device code=$code =====" -Encoding UTF8
exit $code
