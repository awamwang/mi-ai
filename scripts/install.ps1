# 安装本项目最小依赖，并精简 xiaogpt 仅保留 chatgptapi
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
$pip = @($py, "-m", "pip")
$mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"

& $py -m pip install -U pip -i $mirror --disable-pip-version-check
# 先装本体（不解析可选依赖树）
& $py -m pip install "xiaogpt==3.23" --no-deps -i $mirror --disable-pip-version-check
& $py -m pip install `
    "miservice_fork>=2.9.3" `
    "openai>=1" `
    "aiohttp" `
    "rich" `
    "httpx[socks]" `
    "pyyaml>=6" `
    "python-dotenv>=1.0.0" `
    "requests" `
    "lingua-language-detector>=2.0.2" `
    -i $mirror --disable-pip-version-check

& $py -m mi_ai.ensure_deps
Write-Host "安装完成。请复制 .env.example 为 .env 并填写配置。"
