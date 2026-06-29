#!/usr/bin/env pwsh
#requires -Version 5.1
# Blank 一键开发启动脚本（PowerShell 版本）
# 对应 bash 版本的 start.sh，功能保持一致。

param(
    [switch]$NoInstall,
    [switch]$InstallOnly,
    [switch]$WithInfra,
    [switch]$NoInstallDocker,
    [switch]$Check,
    [switch]$Status,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Help
)

if ($Help) {
    $helpText = @"
用法: .\start.ps1 [选项]

选项:
  -NoInstall         跳过自动依赖安装。
  -InstallOnly       仅安装依赖后退出。
  -WithInfra         通过 scripts/infra.sh 启动本地 PostgreSQL、Redis 和 Neo4j。
  -NoInstallDocker   与 -WithInfra 一起使用时，跳过 Linux 下自动安装 Docker。
  -Check             检查环境 readiness 后退出。
  -Status            检查运行状态后退出。
  -BackendPort N     后端端口，默认 8000。
  -FrontendPort N    前端端口，默认 5173。
  -Help              显示此帮助。

环境变量:
  BLANK_BACKEND_HOST   后端绑定主机，默认 127.0.0.1。
  BLANK_FRONTEND_HOST  前端绑定主机，默认 127.0.0.1。
  BACKEND_PORT         后端端口，默认 8000。
  FRONTEND_PORT        前端端口，默认 5173。
"@
    Write-Host $helpText
    exit 0
}

# 从环境变量读取端口默认值
if ($env:BACKEND_PORT) { $BackendPort = [int]$env:BACKEND_PORT }
if ($env:FRONTEND_PORT) { $FrontendPort = [int]$env:FRONTEND_PORT }

$ROOT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BACKEND_DIR = Join-Path $ROOT_DIR "backend"
$PWA_DIR = Join-Path $ROOT_DIR "pwa"
$VENV_PYTHON = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"

$BACKEND_HOST = "127.0.0.1"
$FRONTEND_HOST = "127.0.0.1"

$global:PYTHON_CMD = $null
$global:BACKEND_PID = $null
$global:FRONTEND_PID = $null

function Log {
    param([string]$Message)
    Write-Host "[blank] $Message"
}

function Fail {
    param([string]$Message)
    throw "[blank] $Message"
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
            # 去除首尾引号
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

function Is-LoopbackHost {
    param([string]$HostName)
    return $HostName -in @("127.0.0.1", "localhost", "::1", "[::1]")
}

function Require-ExplicitRemoteSecurity {
    param([string]$ServiceName, [string]$HostName)
    if (Is-LoopbackHost $HostName) { return }
    if ([string]::IsNullOrEmpty($env:BLANK_ALLOWED_HOSTS) -or [string]::IsNullOrEmpty($env:BLANK_CORS_ORIGINS)) {
        Fail "拒绝启动：$ServiceName 绑定在 $HostName；请先设置 BLANK_ALLOWED_HOSTS 和 BLANK_CORS_ORIGINS。"
    }
}

function Display-Host {
    param([string]$HostName)
    if ($HostName -in @("0.0.0.0", "::", "[::]")) { return "127.0.0.1" }
    return $HostName
}

function Url-For {
    param([string]$HostName, [int]$Port)
    return "http://$(Display-Host $HostName):$Port"
}

function Port-InUse {
    param([int]$Port)
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    }
    # 备用方案：netstat
    $out = netstat -ano | Select-String ":$Port\s"
    return $null -ne $out
}

function Tcp-ConnectOk {
    param([string]$HostName, [int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect($HostName, $Port)
        $client.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Service-EndpointFromUrl {
    param([string]$Url)
    try {
        $uri = [System.Uri]$Url
    }
    catch {
        Fail "URL 格式无效: $Url"
    }
    $targetHost = $uri.Host
    $port = $uri.Port
    if ($port -eq -1) {
        $port = switch ($uri.Scheme) {
            "postgresql" { 5432 }
            "postgres" { 5432 }
            "redis" { 6379 }
            "bolt" { 7687 }
            default { 0 }
        }
    }
    return "$targetHost $port"
}

function Require-TcpService {
    param([string]$Name, [string]$Url)
    $endpoint = Service-EndpointFromUrl $Url
    $parts = $endpoint -split " "
    $targetHost = $parts[0]
    $port = [int]$parts[1]
    if ([string]::IsNullOrEmpty($targetHost) -or $port -eq 0) {
        Fail "$Name URL 无效：$Url"
    }
    if (-not (Tcp-ConnectOk $targetHost $port)) {
        Fail "$Name 无法访问：$targetHost`:$port。请启动服务或更新环境变量 URL。"
    }
}

function Check-RequiredServices {
    $dbUrl = if ($env:BLANK_DATABASE_URL) { $env:BLANK_DATABASE_URL } else { "postgresql://blank:blank@127.0.0.1:5432/blank" }
    $redisUrl = if ($env:BLANK_REDIS_URL) { $env:BLANK_REDIS_URL } else { "redis://127.0.0.1:6379/0" }
    Require-TcpService "PostgreSQL" $dbUrl
    Require-TcpService "Redis" $redisUrl
    $graphrag = if ($env:BLANK_GRAPHRAG_ENABLED) { $env:BLANK_GRAPHRAG_ENABLED } else { "true" }
    if ($graphrag -notin @("false", "0", "off")) {
        $neo4jUrl = if ($env:BLANK_NEO4J_URI) { $env:BLANK_NEO4J_URI } else { "bolt://127.0.0.1:7687" }
        Require-TcpService "Neo4j" $neo4jUrl
    }
}

function Start-LocalInfra {
    if (-not $WithInfra) { return }
    Log "正在启动本地 PostgreSQL/Redis/Neo4j 基础设施"
    if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
        Fail "启动基础设施需要 bash。请安装 Git Bash 或使用 WSL。"
    }
    $infraArgs = @("up")
    if ($NoInstallDocker) {
        $infraArgs += "--no-install-docker"
    }
    & bash (Join-Path $ROOT_DIR "scripts/infra.sh") $infraArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "本地基础设施启动失败。请手动启动 PostgreSQL/Redis/Neo4j 或检查 Docker Compose 访问。"
    }
}

function Http-Ok {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Wait-ForHttp {
    param([string]$Name, [string]$Url, [int]$Attempts = 60)
    for ($i = 1; $i -le $Attempts; $i++) {
        if (Http-Ok $Url) { return }
        Start-Sleep -Seconds 0.5
    }
    Fail "$Name 未能就绪：$Url"
}

function Resolve-Python {
    if ($env:CONDA_DEFAULT_ENV -eq "blank-learning" -and $env:CONDA_PREFIX -and (Test-Path (Join-Path $env:CONDA_PREFIX "python.exe"))) {
        $global:PYTHON_CMD = @( (Join-Path $env:CONDA_PREFIX "python.exe") )
        return
    }
    if (Get-Command conda -ErrorAction SilentlyContinue) {
        $envs = conda env list 2>$null | Out-String
        if ($envs -match "blank-learning") {
            $global:PYTHON_CMD = @("conda", "run", "-n", "blank-learning", "python")
            return
        }
    }
    if (Test-Path $VENV_PYTHON) {
        $global:PYTHON_CMD = @($VENV_PYTHON)
        return
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        Log "正在创建后端虚拟环境 backend/.venv"
        & python -m venv (Join-Path $BACKEND_DIR ".venv")
        $global:PYTHON_CMD = @($VENV_PYTHON)
        return
    }
    Fail "未找到 Python。请安装 Python 3 或使用 conda env create -f environment.yml。"
}

function Backend-ImportsOk {
    $pyCode = "import fastapi, uvicorn, pydantic, multipart, pypdf, cryptography"
    $pyArgs = if ($global:PYTHON_CMD.Length -gt 1) { $global:PYTHON_CMD[1..($global:PYTHON_CMD.Length - 1)] } else { @() }
    & $global:PYTHON_CMD[0] $pyArgs -c $pyCode 2>$null
    return $LASTEXITCODE -eq 0
}

function Install-BackendDeps {
    if (Backend-ImportsOk) { return }
    if ($NoInstall) {
        Fail "缺少后端依赖。去掉 -NoInstall 或手动安装 backend/requirements.txt。"
    }
    Log "正在安装后端依赖"
    $pyArgs = if ($global:PYTHON_CMD.Length -gt 1) { $global:PYTHON_CMD[1..($global:PYTHON_CMD.Length - 1)] } else { @() }
    & $global:PYTHON_CMD[0] $pyArgs -m pip install -r (Join-Path $BACKEND_DIR "requirements.txt")
}

function Install-FrontendDeps {
    $nodeExec = $global:NODE_CMD[0]
    $npmExec = $global:NPM_CMD[0]
    if (-not (Get-Command $nodeExec -ErrorAction SilentlyContinue)) {
        Fail "未找到 Node.js。请使用 conda env create -f environment.yml 或安装 Node 22。"
    }
    if (-not (Get-Command $npmExec -ErrorAction SilentlyContinue)) {
        Fail "未找到 npm。"
    }
    if (Test-Path (Join-Path $PWA_DIR "node_modules")) { return }
    if ($NoInstall) {
        Fail "缺少前端依赖。去掉 -NoInstall 或在 pwa/ 下运行 npm install。"
    }
    Log "正在安装前端依赖"
    Push-Location $PWA_DIR
    try {
        $npmArgs = if ($global:NPM_CMD.Length -gt 1) { $global:NPM_CMD[1..($global:NPM_CMD.Length - 1)] } else { @() }
        & $npmExec $npmArgs install
    }
    finally {
        Pop-Location
    }
}

function Already-Running {
    return (Http-Ok "$(Url-For $BACKEND_HOST $BackendPort)/api/health") -and (Http-Ok "$(Url-For $FRONTEND_HOST $FrontendPort)")
}

function Cleanup {
    if ($global:BACKEND_PID) {
        Stop-Process -Id $global:BACKEND_PID -Force -ErrorAction SilentlyContinue
    }
    if ($global:FRONTEND_PID) {
        Stop-Process -Id $global:FRONTEND_PID -Force -ErrorAction SilentlyContinue
    }
}

trap {
    Cleanup
    break
}

function Main {
    Set-Location $ROOT_DIR

    Load-DotEnv
    if ($env:BLANK_BACKEND_HOST) { $script:BACKEND_HOST = $env:BLANK_BACKEND_HOST }
    if ($env:BLANK_FRONTEND_HOST) { $script:FRONTEND_HOST = $env:BLANK_FRONTEND_HOST }

    if ($Check) {
        & (Join-Path $ROOT_DIR "scripts\check-env.ps1")
        exit $LASTEXITCODE
    }
    if ($Status) {
        & (Join-Path $ROOT_DIR "scripts\status.ps1")
        exit 0
    }

    Require-ExplicitRemoteSecurity "backend" $BACKEND_HOST
    Require-ExplicitRemoteSecurity "frontend" $FRONTEND_HOST

    # 自动联网补齐环境（会设置 $global:PYTHON_CMD / NODE_CMD / NPM_CMD）
    $global:INSTALL_DEPS = -not $NoInstall
    . (Join-Path $ROOT_DIR "scripts\bootstrap-env.ps1")
    Initialize-BlankEnv

    if (-not $global:PYTHON_CMD) {
        Resolve-Python
    }
    if (-not $global:NODE_CMD) { $global:NODE_CMD = @("node") }
    if (-not $global:NPM_CMD) { $global:NPM_CMD = @("npm") }
    Install-BackendDeps
    Install-FrontendDeps

    if ($InstallOnly) {
        Log "依赖已准备就绪。"
        exit 0
    }

    Start-LocalInfra
    Check-RequiredServices

    $backendUrl = Url-For $BACKEND_HOST $BackendPort
    $frontendUrl = Url-For $FRONTEND_HOST $FrontendPort

    if (Already-Running) {
        Log "服务已经在运行。"
        Log "前端: $frontendUrl/"
        Log "后端:  $backendUrl/docs"
        exit 0
    }

    if (Port-InUse $BackendPort) {
        Fail "后端端口 $BackendPort 已被占用。"
    }
    if (Port-InUse $FrontendPort) {
        Fail "前端端口 $FrontendPort 已被占用。"
    }

    Log "正在启动后端 $backendUrl"
    $pyArgs = if ($global:PYTHON_CMD.Length -gt 1) { $global:PYTHON_CMD[1..($global:PYTHON_CMD.Length - 1)] } else { @() }
    $backendProc = Start-Process `
        -FilePath $global:PYTHON_CMD[0] `
        -ArgumentList ($pyArgs + @("-m", "uvicorn", "backend.app.main:app", "--host", $BACKEND_HOST, "--port", "$BackendPort", "--reload", "--no-server-header")) `
        -PassThru -NoNewWindow -WorkingDirectory $ROOT_DIR
    $global:BACKEND_PID = $backendProc.Id
    Wait-ForHttp "Backend" "$backendUrl/api/health" 80

    Log "正在启动前端 $frontendUrl"
    $env:VITE_API_BASE_URL = if ($env:VITE_API_BASE_URL) { $env:VITE_API_BASE_URL } else { $backendUrl }
    $npmArgs = if ($global:NPM_CMD.Length -gt 1) { $global:NPM_CMD[1..($global:NPM_CMD.Length - 1)] } else { @() }
    $frontendProc = Start-Process `
        -FilePath $global:NPM_CMD[0] `
        -ArgumentList ($npmArgs + @("run", "dev", "--", "--host", $FRONTEND_HOST, "--port", "$FrontendPort")) `
        -PassThru -NoNewWindow -WorkingDirectory $PWA_DIR
    $global:FRONTEND_PID = $frontendProc.Id
    Wait-ForHttp "Frontend" $frontendUrl 80

    Log "准备就绪。"
    Log "前端: $frontendUrl/"
    Log "后端:  $backendUrl/docs"
    Log "按 Ctrl+C 停止两个服务。"

    # 等待任一子进程退出
    while ($true) {
        $backendAlive = $false
        $frontendAlive = $false
        try {
            $b = Get-Process -Id $global:BACKEND_PID -ErrorAction Stop
            $backendAlive = -not $b.HasExited
        }
        catch { $backendAlive = $false }
        try {
            $f = Get-Process -Id $global:FRONTEND_PID -ErrorAction Stop
            $frontendAlive = -not $f.HasExited
        }
        catch { $frontendAlive = $false }

        if (-not $backendAlive -or -not $frontendAlive) { break }
        Start-Sleep -Seconds 1
    }

    Cleanup
}

Main
