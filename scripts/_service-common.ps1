# 服务脚本共用常量与工具函数（由其他脚本点源引入）
$ErrorActionPreference = "Stop"

$script:MiAiRoot = Split-Path -Parent $PSScriptRoot
$script:MiAiTaskName = "awam-mi-ai"
$script:MiAiWatchdogPidFile = Join-Path $MiAiRoot "logs\watchdog.pid"
$script:MiAiStableSeconds = 60

function Get-MiAiDotEnvValue {
    param(
        [Parameter(Mandatory)][string]$Key,
        [string]$Default = ""
    )
    $envPath = Join-Path $MiAiRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        return $Default
    }
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        $trim = $line.Trim()
        if ($trim -eq "" -or $trim.StartsWith("#")) {
            continue
        }
        $eq = $trim.IndexOf("=")
        if ($eq -lt 1) {
            continue
        }
        $name = $trim.Substring(0, $eq).Trim()
        if ($name -ne $Key) {
            continue
        }
        $value = $trim.Substring($eq + 1).Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        return $value
    }
    return $Default
}

function Get-MiAiServiceConfig {
    $devicesRaw = Get-MiAiDotEnvValue -Key "MI_AI_DEVICES" -Default "LX06,L05C"
    $devices = @()
    foreach ($part in ($devicesRaw -split "[,;\s]+")) {
        $d = $part.Trim().ToUpperInvariant()
        if ($d -ne "") {
            $devices += $d
        }
    }
    if ($devices.Count -eq 0) {
        $devices = @("LX06", "L05C")
    }

    $baseSec = 5
    $maxSec = 300
    $keepDays = 7
    $logDirName = "logs"

    $parsed = 0
    if ([int]::TryParse((Get-MiAiDotEnvValue -Key "MI_AI_RESTART_BASE_SEC" -Default "5"), [ref]$parsed)) {
        $baseSec = [Math]::Max(1, $parsed)
    }
    if ([int]::TryParse((Get-MiAiDotEnvValue -Key "MI_AI_RESTART_MAX_SEC" -Default "300"), [ref]$parsed)) {
        $maxSec = [Math]::Max($baseSec, $parsed)
    }
    if ([int]::TryParse((Get-MiAiDotEnvValue -Key "MI_AI_LOG_KEEP_DAYS" -Default "7"), [ref]$parsed)) {
        $keepDays = [Math]::Max(1, $parsed)
    }
    $logDirRaw = Get-MiAiDotEnvValue -Key "MI_AI_LOG_DIR" -Default "logs"
    if ($logDirRaw.Trim() -ne "") {
        $logDirName = $logDirRaw.Trim().TrimEnd("\", "/")
    }

    $logDir = $logDirName
    if (-not [System.IO.Path]::IsPathRooted($logDir)) {
        $logDir = Join-Path $MiAiRoot $logDir
    }

    return [pscustomobject]@{
        Devices         = $devices
        RestartBaseSec  = $baseSec
        RestartMaxSec   = $maxSec
        LogKeepDays     = $keepDays
        LogDir          = $logDir
        PythonExe       = Join-Path $MiAiRoot ".venv\Scripts\python.exe"
        WatchdogScript  = Join-Path $PSScriptRoot "watchdog.ps1"
        RunDeviceScript = Join-Path $PSScriptRoot "run-device.ps1"
    }
}

function Ensure-MiAiLogDir {
    param([Parameter(Mandatory)][string]$LogDir)
    if (-not (Test-Path -LiteralPath $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
}

function Get-MiAiDailyLogPath {
    param(
        [Parameter(Mandatory)][string]$LogDir,
        [Parameter(Mandatory)][string]$Prefix
    )
    $day = Get-Date -Format "yyyy-MM-dd"
    return Join-Path $LogDir ("{0}-{1}.log" -f $Prefix, $day)
}

function Write-MiAiLog {
    param(
        [Parameter(Mandatory)][string]$LogPath,
        [Parameter(Mandatory)][string]$Message
    )
    $dir = Split-Path -Parent $LogPath
    Ensure-MiAiLogDir -LogDir $dir
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
}

function Clear-MiAiOldLogs {
    param(
        [Parameter(Mandatory)][string]$LogDir,
        [Parameter(Mandatory)][int]$KeepDays
    )
    if (-not (Test-Path -LiteralPath $LogDir)) {
        return
    }
    $cutoff = (Get-Date).Date.AddDays(-$KeepDays)
    Get-ChildItem -LiteralPath $LogDir -File -Filter "*.log" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        }
}

function Get-MiAiProcessByPid {
    param([int]$ProcessId)
    if ($ProcessId -le 0) {
        return $null
    }
    try {
        return Get-Process -Id $ProcessId -ErrorAction Stop
    }
    catch {
        return $null
    }
}

function Read-MiAiPidFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }
    $raw = (Get-Content -LiteralPath $Path -TotalCount 1 -ErrorAction SilentlyContinue)
    $pidVal = 0
    if ([int]::TryParse("$raw".Trim(), [ref]$pidVal)) {
        return $pidVal
    }
    return 0
}

function Write-MiAiPidFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][int]$ProcessId
    )
    $dir = Split-Path -Parent $Path
    Ensure-MiAiLogDir -LogDir $dir
    Set-Content -LiteralPath $Path -Value "$ProcessId" -Encoding ASCII -NoNewline
}

function Stop-MiAiProcessTree {
    param([int]$ProcessId)
    if ($ProcessId -le 0) {
        return
    }
    $proc = Get-MiAiProcessByPid -ProcessId $ProcessId
    if (-not $proc) {
        return
    }
    # /T 结束整棵进程树，避免留下 python 孤儿
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
    Start-Sleep -Milliseconds 300
}

function Test-MiAiWatchdogRunning {
    $cfg = Get-MiAiServiceConfig
    $pidFile = Join-Path $cfg.LogDir "watchdog.pid"
    $wid = Read-MiAiPidFile -Path $pidFile
    $proc = Get-MiAiProcessByPid -ProcessId $wid
    if ($proc) {
        return [pscustomobject]@{ Running = $true; Pid = $wid; PidFile = $pidFile }
    }
    return [pscustomobject]@{ Running = $false; Pid = 0; PidFile = $pidFile }
}

function Get-MiAiBackoffSeconds {
    param(
        [Parameter(Mandatory)][int]$FailCount,
        [Parameter(Mandatory)][int]$BaseSec,
        [Parameter(Mandatory)][int]$MaxSec
    )
    # 第 1 次失败用 base，之后按 2^(n-1) 指数增长
    $exp = [Math]::Max(0, $FailCount - 1)
    $delay = [double]$BaseSec * [Math]::Pow(2, $exp)
    if ($delay -gt $MaxSec) {
        $delay = $MaxSec
    }
    return [int][Math]::Round($delay)
}
