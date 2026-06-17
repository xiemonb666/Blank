# 检查 Blank 运行环境是否就绪（PowerShell 版本）
# 数据库连接问题只作为状态项报告，不会导致脚本失败。

param()

$ROOT_DIR = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR = Join-Path $ROOT_DIR "backend"
$PWA_DIR = Join-Path $ROOT_DIR "pwa"
$script:CORE_OK = $true

function Print-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host "[blank] $Title"
    Write-Host "  $("项目".PadRight(22)) $("状态".PadRight(10)) 说明"
}

function Print-Row {
    param([string]$Item, [string]$Status, [string]$Detail)
    Write-Host "  $($Item.PadRight(22)) $($Status.PadRight(10)) $Detail"
}

function Load-DotEnv {
    $envPath = Join-Path $ROOT_DIR ".env"
    if (-not (Test-Path $envPath)) { return }
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) { return }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $key = $matches[1]
            $value = $matches[2].Trim()
            if (($value.Length -ge 2) -and (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            )) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Test-Command {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Check-Python {
    $py = $null
    foreach ($candidate in @("python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            try {
                $ver = & $cmd.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null | Out-String
                if ($ver.Trim()) {
                    $py = $cmd.Source
                    break
                }
            }
            catch {}
        }
    }
    if (-not $py) {
        Print-Row "Python" "缺失" "未找到可用的 python/python3"
        $script:CORE_OK = $false
        return
    }
    $verStr = (& $py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null).Trim()
    $major = [int]($verStr.Split('.')[0])
    $minor = [int]($verStr.Split('.')[1])
    if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 13)) {
        Print-Row "Python" "就绪" $verStr
    }
    else {
        Print-Row "Python" "版本过低" "$verStr（需要 ≥3.13）"
        $script:CORE_OK = $false
    }
}

function Check-Node {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Print-Row "Node.js" "缺失" "未找到 node"
        $script:CORE_OK = $false
        return
    }
    $ver = (& $cmd.Source --version 2>$null).Trim().TrimStart('v')
    $major = [int]($ver.Split('.')[0])
    if ($major -ge 22) {
        Print-Row "Node.js" "就绪" $ver
    }
    else {
        Print-Row "Node.js" "版本过低" "$ver（需要 ≥22）"
        $script:CORE_OK = $false
    }
}

function Conda-EnvExists {
    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $conda) { return $false }
    $match = & $conda.Source env list 2>$null |
        Where-Object { $_ -match "^blank-learning\s" } |
        Select-Object -First 1
    return $null -ne $match
}

function Check-PythonEnv {
    if (Conda-EnvExists) {
        Print-Row "Python 环境" "就绪" "blank-learning conda 环境"
        return
    }
    $venvPython = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Print-Row "Python 环境" "就绪" "backend/.venv"
        return
    }
    Print-Row "Python 环境" "缺失" "无 blank-learning conda 环境或 backend/.venv"
    $script:CORE_OK = $false
}

function Check-BackendImports {
    $py = $null
    foreach ($candidate in @("python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            & $cmd.Source -c "import sys" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $py = $cmd.Source
                break
            }
        }
        catch {}
    }
    $venvPython = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $py = $venvPython
    }
    elseif (Conda-EnvExists) {
        $conda = (Get-Command conda).Source
        $py = @($conda, "run", "--no-capture-output", "-n", "blank-learning", "python")
    }
    if (-not $py) {
        Print-Row "Backend 依赖" "缺失" "未找到可用的 Python"
        $script:CORE_OK = $false
        return
    }
    $code = "import fastapi, uvicorn, pydantic, multipart, pypdf, cryptography"
    if ($py -is [array]) {
        $args = if ($py.Length -gt 1) { $py[1..($py.Length - 1)] } else { @() }
        & $py[0] $args -c $code 2>$null | Out-Null
    }
    else {
        & $py -c $code 2>$null | Out-Null
    }
    if ($LASTEXITCODE -eq 0) {
        Print-Row "Backend 依赖" "就绪" "关键包可导入"
    }
    else {
        Print-Row "Backend 依赖" "缺失" "请运行 .\start.ps1 -InstallOnly"
        $script:CORE_OK = $false
    }
}

function Check-NodeModules {
    if (Test-Path (Join-Path $PWA_DIR "node_modules")) {
        Print-Row "Frontend 依赖" "就绪" "node_modules 已存在"
    }
    else {
        Print-Row "Frontend 依赖" "缺失" "请运行 .\start.ps1 -InstallOnly"
        $script:CORE_OK = $false
    }
}

function Check-Docker {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Print-Row "Docker" "缺失" "Linux 下可用 -WithInfra 自动安装"
        return
    }
    try {
        & $docker.Source compose version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Print-Row "Docker" "就绪" "docker compose 可用"
        }
        else {
            Print-Row "Docker" "部分" "docker 存在但 compose 插件缺失"
        }
    }
    catch {
        Print-Row "Docker" "部分" "docker 存在但 compose 插件缺失"
    }
}

function Tcp-ConnectOk {
    param([string]$HostName, [int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect($HostName, $Port)
        $client.Close()
        return $true
    }
    catch { return $false }
}

function Parse-UrlHostPort {
    param([string]$Url, [int]$DefaultPort)
    try {
        $uri = [System.Uri]$Url
        $port = if ($uri.Port -gt 0) { $uri.Port } else { $DefaultPort }
        return "$($uri.Host) $port"
    }
    catch {
        return "127.0.0.1 $DefaultPort"
    }
}

function Check-Services {
    $dbUrl = if ($env:BLANK_DATABASE_URL) { $env:BLANK_DATABASE_URL } else { "postgresql://blank:blank@127.0.0.1:5432/blank" }
    $redisUrl = if ($env:BLANK_REDIS_URL) { $env:BLANK_REDIS_URL } else { "redis://127.0.0.1:6379/0" }
    $neo4jUrl = if ($env:BLANK_NEO4J_URI) { $env:BLANK_NEO4J_URI } else { "bolt://127.0.0.1:7687" }

    $db = Parse-UrlHostPort $dbUrl 5432
    $redis = Parse-UrlHostPort $redisUrl 6379
    $neo4j = Parse-UrlHostPort $neo4jUrl 7687

    $dbParts = $db -split " "
    if (Tcp-ConnectOk $dbParts[0] ([int]$dbParts[1])) {
        Print-Row "PostgreSQL" "可达" "$($dbParts[0]):$($dbParts[1])"
    }
    else {
        Print-Row "PostgreSQL" "不可达" "$($dbParts[0]):$($dbParts[1])（可 .\start.ps1 -WithInfra 启动）"
    }

    $redisParts = $redis -split " "
    if (Tcp-ConnectOk $redisParts[0] ([int]$redisParts[1])) {
        Print-Row "Redis" "可达" "$($redisParts[0]):$($redisParts[1])"
    }
    else {
        Print-Row "Redis" "不可达" "$($redisParts[0]):$($redisParts[1])"
    }

    if ($env:BLANK_GRAPHRAG_ENABLED -eq "false" -or $env:BLANK_GRAPHRAG_ENABLED -eq "0") {
        Print-Row "Neo4j" "已禁用" "BLANK_GRAPHRAG_ENABLED=false"
    }
    else {
        $neo4jParts = $neo4j -split " "
        if (Tcp-ConnectOk $neo4jParts[0] ([int]$neo4jParts[1])) {
            Print-Row "Neo4j" "可达" "$($neo4jParts[0]):$($neo4jParts[1])"
        }
        else {
            Print-Row "Neo4j" "不可达" "$($neo4jParts[0]):$($neo4jParts[1])"
        }
    }
}

Load-DotEnv
Print-Header "环境检查"
Check-Python
Check-Node
Check-PythonEnv
Check-BackendImports
Check-NodeModules
Check-Docker
Check-Services

Write-Host ""
if ($script:CORE_OK) {
    Write-Host "[blank] 核心环境已就绪，可直接运行 .\start.ps1"
    exit 0
}
else {
    Write-Host "[blank] 核心环境有缺失，建议运行 .\start.ps1 -InstallOnly 或 .\start.ps1 -WithInfra"
    exit 1
}
