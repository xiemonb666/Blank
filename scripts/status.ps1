# 检查 Blank 运行状态（PowerShell 版本）
# 数据库连接问题只作为状态项报告，不会导致脚本失败。

param()

$ROOT_DIR = Split-Path -Parent $PSScriptRoot
$COMPOSE_FILE = Join-Path $ROOT_DIR "compose.yaml"

$BACKEND_HOST = "127.0.0.1"
$FRONTEND_HOST = "127.0.0.1"
$BackendPort = 8000
$FrontendPort = 5173

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

function Display-HostName {
    param([string]$HostName)
    if ($HostName -in @("0.0.0.0", "::", "[::]")) { return "127.0.0.1" }
    return $HostName
}

function Url-For {
    param([string]$HostName, [int]$Port)
    return "http://$(Display-HostName $HostName):$Port"
}

function Http-Ok {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch { return $false }
}

function Port-InUse {
    param([int]$Port)
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    }
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

function Check-ServiceHttp {
    param([string]$Name, [string]$Url)
    if (Http-Ok $Url) {
        Print-Row "$Name HTTP" "可达" $Url
    }
    else {
        Print-Row "$Name HTTP" "不可达" $Url
    }
}

function Check-ServicePort {
    param([string]$Name, [int]$Port)
    if (Port-InUse $Port) {
        Print-Row "$Name 端口" "监听中" "端口 $Port"
    }
    else {
        Print-Row "$Name 端口" "未监听" "端口 $Port"
    }
}

function Check-DockerContainers {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Print-Row "Docker 容器" "未知" "未检测到 docker"
        return
    }
    try {
        & $docker.Source compose version 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Print-Row "Docker 容器" "未知" "docker compose 插件缺失"
            return
        }
        $output = & $docker.Source compose -f $COMPOSE_FILE ps --format json 2>$null | Out-String
        if ($output.Trim() -and $output.Trim() -ne "[]") {
            Print-Row "Docker 容器" "运行中" "详见 docker compose -f compose.yaml ps"
        }
        else {
            Print-Row "Docker 容器" "未运行" "可 .\start.ps1 -WithInfra 启动"
        }
    }
    catch {
        Print-Row "Docker 容器" "未知" "无法获取容器状态"
    }
}

function Check-DbServices {
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
        Print-Row "PostgreSQL" "不可达" "$($dbParts[0]):$($dbParts[1])"
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
if ($env:BLANK_BACKEND_HOST) { $script:BACKEND_HOST = $env:BLANK_BACKEND_HOST }
if ($env:BLANK_FRONTEND_HOST) { $script:FRONTEND_HOST = $env:BLANK_FRONTEND_HOST }
if ($env:BACKEND_PORT) { $BackendPort = [int]$env:BACKEND_PORT }
if ($env:FRONTEND_PORT) { $FrontendPort = [int]$env:FRONTEND_PORT }

Print-Header "运行状态检查"
Check-ServiceHttp "后端" "$(Url-For $BACKEND_HOST $BackendPort)/api/health"
Check-ServicePort "后端" $BackendPort
Check-ServiceHttp "前端" "$(Url-For $FRONTEND_HOST $FrontendPort)"
Check-ServicePort "前端" $FrontendPort
Check-DockerContainers
Check-DbServices

Write-Host ""
Write-Host "[blank] 状态检查完成（数据库不可达不会阻止其他服务判定）"
exit 0
