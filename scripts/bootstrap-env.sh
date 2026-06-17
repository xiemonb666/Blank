#!/usr/bin/env bash
# 自动联网补齐 Blank 运行环境（Bash 版本，支持 Linux / macOS / WSL）
# 供 start.sh source 使用。
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKEND_DIR="${ROOT_DIR}/backend"
PWA_DIR="${ROOT_DIR}/pwa"
TOOLS_DIR="${ROOT_DIR}/.tools"
MINIFORGE_DIR="${TOOLS_DIR}/miniforge3"
ENV_NAME="blank-learning"
INSTALL_DEPS="${INSTALL_DEPS:-1}"

_blank_env_log() {
  printf '[blank-env] %s\n' "$*"
}

_blank_env_fail() {
  printf '[blank-env] %s\n' "$*" >&2
  exit 1
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

conda_executable() {
  if [[ -x "${MINIFORGE_DIR}/bin/conda" ]]; then
    printf '%s' "${MINIFORGE_DIR}/bin/conda"
    return
  fi
  if has_command conda; then
    command -v conda
    return
  fi
}

conda_env_exists() {
  local conda
  conda="$(conda_executable)" || return 1
  "${conda}" env list 2>/dev/null | awk '{print $1}' | grep -qx "${ENV_NAME}"
}

conda_env_prefix() {
  local conda
  conda="$(conda_executable)" || return 1
  "${conda}" env list 2>/dev/null | awk -v name="${ENV_NAME}" '$1 == name {print $NF; exit}'
}

python_ok() {
  local py="$1"
  "${py}" -c "import sys; assert sys.version_info >= (3, 12)" >/dev/null 2>&1
}

node_ok() {
  local node="$1"
  "${node}" --version >/dev/null 2>&1
}

sha256_verify() {
  local file="$1"
  local expected="$2"
  local actual
  if has_command sha256sum; then
    actual="$(sha256sum "${file}" | awk '{print $1}')"
  elif has_command shasum; then
    actual="$(shasum -a 256 "${file}" | awk '{print $1}')"
  else
    _blank_env_log "警告：未找到 sha256sum/shasum，跳过安装包校验"
    return 0
  fi
  if [[ "${actual}" != "${expected}" ]]; then
    _blank_env_fail "安装包 SHA256 校验失败（期望 ${expected}，实际 ${actual}）"
  fi
}

detect_miniforge_suffix() {
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"
  case "${os}" in
    Linux)
      case "${arch}" in
        x86_64) printf 'Linux-x86_64.sh' ;;
        aarch64|arm64) printf 'Linux-aarch64.sh' ;;
        *) _blank_env_fail "不支持的 Linux 架构：${arch}" ;;
      esac
      ;;
    Darwin)
      case "${arch}" in
        x86_64|amd64) printf 'MacOSX-x86_64.sh' ;;
        arm64|aarch64) printf 'MacOSX-arm64.sh' ;;
        *) _blank_env_fail "不支持的 macOS 架构：${arch}" ;;
      esac
      ;;
    *)
      _blank_env_fail "本 Bash 引导脚本不支持 ${os}。Windows 请使用 start.ps1。"
      ;;
  esac
}

curl_download() {
  local url="$1"
  local out="$2"
  if has_command curl; then
    curl -fsSL --max-time 300 -o "${out}" "${url}"
  elif has_command wget; then
    wget -q --timeout=300 -O "${out}" "${url}"
  else
    _blank_env_fail "需要 curl 或 wget 才能联网下载环境。"
  fi
}

install_local_miniforge() {
  local suffix installer_url sha_url installer_file sha_file expected
  suffix="$(detect_miniforge_suffix)"
  installer_url="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${suffix}"
  sha_url="${installer_url}.sha256"
  installer_file="${TOOLS_DIR}/miniforge3-installer.sh"
  sha_file="${installer_file}.sha256"

  mkdir -p "${TOOLS_DIR}"
  _blank_env_log "正在下载 Miniforge 安装包"
  curl_download "${installer_url}" "${installer_file}"
  _blank_env_log "正在下载 SHA256 校验文件"
  curl_download "${sha_url}" "${sha_file}"

  expected="$(awk '{print $1}' "${sha_file}")"
  sha256_verify "${installer_file}" "${expected}"

  _blank_env_log "正在安装本地 Miniforge 到 ${MINIFORGE_DIR}"
  rm -rf "${MINIFORGE_DIR}"
  bash "${installer_file}" -b -p "${MINIFORGE_DIR}"
  rm -f "${installer_file}" "${sha_file}"
}

create_conda_env() {
  local conda
  conda="$(conda_executable)"
  if conda_env_exists; then
    _blank_env_log "更新 conda 环境 ${ENV_NAME}"
    "${conda}" env update -n "${ENV_NAME}" -f "${ROOT_DIR}/environment.yml" --prune
  else
    _blank_env_log "创建 conda 环境 ${ENV_NAME}"
    "${conda}" env create -f "${ROOT_DIR}/environment.yml"
  fi
}

set_conda_env_paths() {
  local env_prefix="$1"
  # 将本地 conda 和当前 env 的 bin 加入 PATH，使命令可被直接调用
  export PATH="${MINIFORGE_DIR}/bin:${env_prefix}/bin:${PATH}"
  export CONDA_DEFAULT_ENV="${ENV_NAME}"
  export CONDA_PREFIX="${env_prefix}"
}

set_conda_commands() {
  local conda
  conda="$(conda_executable)" || _blank_env_fail "找不到可用的 conda"
  # 使用 conda run，兼容 Windows Git Bash / Linux / macOS，且不需要硬编码 env 内可执行文件路径
  PYTHON_CMD=("${conda}" "run" "--no-capture-output" "-n" "${ENV_NAME}" "python")
  NODE_CMD=("${conda}" "run" "--no-capture-output" "-n" "${ENV_NAME}" "node")
  NPM_CMD=("${conda}" "run" "--no-capture-output" "-n" "${ENV_NAME}" "npm")
}

bootstrap_env() {
  local env_prefix

  # 快速路径 1：blank-learning conda 环境已存在（系统或本地）
  if conda_env_exists; then
    env_prefix="$(conda_env_prefix)"
    _blank_env_log "检测到 conda 环境 ${ENV_NAME}：${env_prefix}"
    set_conda_env_paths "${env_prefix}"
    set_conda_commands
    return
  fi

  # 快速路径 2：系统已有 python3 + node，并且 python 版本足够
  if has_command python3 && python_ok python3 && has_command node && node_ok node; then
    _blank_env_log "检测到系统 Python/Node，使用现有工具链"
    PYTHON_CMD=(python3)
    NODE_CMD=(node)
    NPM_CMD=(npm)
    return
  fi

  if [[ "${INSTALL_DEPS}" != "1" ]]; then
    _blank_env_fail "缺少运行环境且指定了 --no-install。请手动安装 Python 3.13 + Node.js 22，或创建 blank-learning conda 环境。"
  fi

  # 需要联网补齐
  if ! has_command python3 || ! has_command node; then
    if ! has_command curl && ! has_command wget; then
      _blank_env_fail "缺少 curl/wget，无法联网下载 Miniforge。请先安装 Python 3.13 和 Node.js 22。"
    fi
    install_local_miniforge
    create_conda_env
  fi

  # 安装/补齐完成后，重新获取环境路径
  if conda_env_exists; then
    env_prefix="$(conda_env_prefix)"
    set_conda_env_paths "${env_prefix}"
    set_conda_commands
  else
    # 兜底：使用系统命令
    PYTHON_CMD=(python3)
    NODE_CMD=(node)
    NPM_CMD=(npm)
  fi
}

# 当脚本被直接执行时，执行一次引导并导出变量（便于 source 或 eval）
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  bootstrap_env
  printf 'PYTHON_CMD=%q\n' "${PYTHON_CMD[*]}"
  printf 'NODE_CMD=%q\n' "${NODE_CMD[*]}"
  printf 'NPM_CMD=%q\n' "${NPM_CMD[*]}"
fi
