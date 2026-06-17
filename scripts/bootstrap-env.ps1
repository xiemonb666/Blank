# 自动联网补齐 Blank 运行环境（PowerShell 版本，支持 Windows）
# 由 start.ps1 dot-source 调用。

function Initialize-BlankEnv {
    param()

    $script:ROOT_DIR = if ($global:ROOT_DIR) { $global:ROOT_DIR } else { Split-Path -Parent $PSScriptRoot }
    $script:BACKEND_DIR = Join-Path $script:ROOT_DIR "backend"
    $script:PWA_DIR = Join-Path $script:ROOT_DIR "pwa"
    $script:TOOLS_DIR = Join-Path $script:ROOT_DIR ".tools"
    $script:MINIFORGE_DIR = Join-Path $script:TOOLS_DIR "miniforge3"
    $script:ENV_NAME = "blank-learning"
    $script:INSTALL_DEPS = if ($null -ne $global:INSTALL_DEPS) { $global:INSTALL_DEPS } else { $true }

    function Log {
        param([string]$Message)
        Write-Host "[blank-env] $Message"
    }

    function Fail {
        param([string]$Message)
        throw "[blank-env] $Message"
    }

    function Has-Command {
        param([string]$Name)
        return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
    }

    function Conda-Exe {
        $localConda = Join-Path $script:MINIFORGE_DIR "Scripts\conda.exe"
        if (Test-Path $localConda) { return $localConda }
        $sysConda = Get-Command conda -ErrorAction SilentlyContinue
        if ($sysConda) { return $sysConda.Source }
        return $null
    }

    function Conda-EnvExists {
        $conda = Conda-Exe
        if (-not $conda) { return $false }
        $match = & $conda env list 2>$null |
            Where-Object { $_ -match "^$([regex]::Escape($script:ENV_NAME))\s" } |
            Select-Object -First 1
        return $null -ne $match
    }

    function Conda-EnvPrefix {
        $conda = Conda-Exe
        if (-not $conda) { return $null }
        $line = (& $conda env list 2>$null | Where-Object { $_ -match "^$([regex]::Escape($script:ENV_NAME))\s+" }) | Select-Object -First 1
        if ($line -match "^\S+\s+(\S+)") { return $Matches[1] }
        return $null
    }

    function Python-Ok {
        param([string]$Path)
        try {
            & $Path -c "import sys; assert sys.version_info >= (3, 12)" 2>$null
            return $LASTEXITCODE -eq 0
        }
        catch { return $false }
    }

    function Backend-ImportsOk {
        param([string]$Path)
        try {
            & $Path -c "import fastapi, uvicorn, pydantic, multipart, pypdf, cryptography" 2>$null
            return $LASTEXITCODE -eq 0
        }
        catch { return $false }
    }

    function Node-Ok {
        param([string]$Path)
        try {
            & $Path --version 2>$null | Out-Null
            return $LASTEXITCODE -eq 0
        }
        catch { return $false }
    }

    function NodeModules-Ok {
        return Test-Path (Join-Path $script:PWA_DIR "node_modules")
    }

    function Download-File {
        param([string]$Url, [string]$OutFile)
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 300 -ErrorAction Stop
        }
        catch {
            Fail "下载失败：${Url}`n$_"
        }
    }

    function Verify-Sha256 {
        param([string]$File, [string]$Expected)
        if (-not $Expected) { return }
        $hash = (Get-FileHash -Path $File -Algorithm SHA256).Hash
        if ($hash -ne $Expected) {
            Fail "SHA256 校验失败：期望 ${Expected}，实际 ${hash}"
        }
    }

    function Install-LocalMiniforge {
        $suffix = "Windows-x86_64.exe"
        $installerUrl = "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${suffix}"
        $shaUrl = "${installerUrl}.sha256"
        $installerFile = Join-Path $script:TOOLS_DIR "miniforge3-installer.exe"
        $shaFile = "${installerFile}.sha256"

        New-Item -ItemType Directory -Force -Path $script:TOOLS_DIR | Out-Null
        Log "正在下载 Miniforge 安装包"
        Download-File $installerUrl $installerFile
        Log "正在下载 SHA256 校验文件"
        Download-File $shaUrl $shaFile

        $expected = (Get-Content $shaFile -TotalCount 1).Trim().Split()[0]
        Verify-Sha256 $installerFile $expected

        Log "正在安装本地 Miniforge 到 $($script:MINIFORGE_DIR)"
        if (Test-Path $script:MINIFORGE_DIR) { Remove-Item -Recurse -Force $script:MINIFORGE_DIR }
        $arg = "/D=$($script:MINIFORGE_DIR)"
        $proc = Start-Process -FilePath $installerFile -ArgumentList @('/S', $arg) -Wait -PassThru
        if ($proc.ExitCode -ne 0) { Fail "Miniforge 安装失败，退出码 $($proc.ExitCode)" }
        Remove-Item -Force $installerFile, $shaFile -ErrorAction SilentlyContinue
    }

    function Create-CondaEnv {
        $conda = Conda-Exe
        if (-not $conda) { Fail "找不到可用的 conda" }
        if (Conda-EnvExists) {
            Log "更新 conda 环境 $ENV_NAME"
            & $conda env update -n $script:ENV_NAME -f (Join-Path $script:ROOT_DIR "environment.yml") --prune
            if ($LASTEXITCODE -ne 0) { Fail "conda env update 失败" }
        }
        else {
            Log "创建 conda 环境 $ENV_NAME"
            & $conda env create -f (Join-Path $script:ROOT_DIR "environment.yml")
            if ($LASTEXITCODE -ne 0) { Fail "conda env create 失败" }
        }
    }

    function Set-CondaCommands {
        $conda = Conda-Exe
        if (-not $conda) { Fail "找不到可用的 conda" }
        # 使用 conda 的绝对路径，避免本地安装后未加入 PATH 导致找不到
        $global:PYTHON_CMD = @($conda, "run", "--no-capture-output", "-n", $script:ENV_NAME, "python")
        $global:NODE_CMD = @($conda, "run", "--no-capture-output", "-n", $script:ENV_NAME, "node")
        $global:NPM_CMD = @($conda, "run", "--no-capture-output", "-n", $script:ENV_NAME, "npm")
    }

    # 快速路径 1：blank-learning conda 环境已存在
    if (Conda-EnvExists) {
        $prefix = Conda-EnvPrefix
        Log "检测到 conda 环境 $ENV_NAME：$prefix"
        Set-CondaCommands
        return
    }

    # 快速路径 2：系统已有 python + node
    $sysPython = Get-Command python -ErrorAction SilentlyContinue
    $sysNode = Get-Command node -ErrorAction SilentlyContinue
    if ($sysPython -and (Python-Ok $sysPython.Source) -and $sysNode -and (Node-Ok $sysNode.Source)) {
        Log "检测到系统 Python/Node，使用现有工具链"
        $global:PYTHON_CMD = @($sysPython.Source)
        $global:NODE_CMD = @($sysNode.Source)
        $npm = Get-Command npm -ErrorAction SilentlyContinue
        $global:NPM_CMD = if ($npm) { @($npm.Source) } else { @("npm") }
        return
    }

    if (-not $script:INSTALL_DEPS) {
        Fail "缺少运行环境且指定了 -NoInstall。请手动安装 Python 3.13 + Node.js 22，或创建 blank-learning conda 环境。"
    }

    # 需要联网补齐
    $needPython = -not ($sysPython -and (Python-Ok $sysPython.Source))
    $needNode = -not ($sysNode -and (Node-Ok $sysNode.Source))

    if ($needPython -or $needNode) {
        if (-not ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows))) {
            Fail "PowerShell 引导脚本仅支持 Windows。其他系统请使用 start.sh。"
        }
        Install-LocalMiniforge
        Create-CondaEnv
        Set-CondaCommands
    }
    else {
        # 兜底：命令存在但前面未返回（理论上不会到达）
        $global:PYTHON_CMD = @($sysPython.Source)
        $global:NODE_CMD = @($sysNode.Source)
        $global:NPM_CMD = if ($npm) { @($npm.Source) } else { @("npm") }
    }
}
