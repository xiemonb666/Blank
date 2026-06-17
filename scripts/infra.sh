#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/compose.yaml"
NO_INSTALL_DOCKER=0

usage() {
  cat <<'EOF'
Usage: ./scripts/infra.sh [options] <command>

Commands:
  up       Start local PostgreSQL, Redis and Neo4j for development.
  down     Stop local infrastructure containers.
  status   Show local infrastructure status.
  logs     Follow local infrastructure logs.

Options:
  --no-install-docker   Skip automatic Docker installation on Linux.

All services bind to 127.0.0.1 only. This script is for development, not production.
EOF
}

log() {
  printf '[infra] %s\n' "$*"
}

fail() {
  printf '[infra] %s\n' "$*" >&2
  exit 1
}

docker_available() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose -f "${COMPOSE_FILE}" "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f "${COMPOSE_FILE}" "$@"
    return
  fi
  echo "Docker Compose is required. Install Docker with the compose plugin, or start PostgreSQL/Redis/Neo4j manually." >&2
  return 1
}

install_docker_linux() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    return 1
  fi
  log "检测到 Linux 且未安装 Docker，正在自动安装..."

  local installer="/tmp/get-docker.sh"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com -o "${installer}"
  elif command -v wget >/dev/null 2>&1; then
    wget -q https://get.docker.com -O "${installer}"
  else
    fail "需要 curl 或 wget 才能下载 Docker 安装脚本。"
  fi

  if [[ "$(id -u)" == "0" ]]; then
    sh "${installer}"
  elif command -v sudo >/dev/null 2>&1; then
    sudo sh "${installer}"
  else
    rm -f "${installer}"
    fail "自动安装 Docker 需要 root 或 sudo 权限。"
  fi
  rm -f "${installer}"

  log "尝试启动 Docker 服务..."
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl start docker || systemctl start docker || true
  elif command -v service >/dev/null 2>&1; then
    sudo service docker start || service docker start || true
  fi

  # 将当前用户加入 docker 组（安装脚本通常已做，这里确保）
  if command -v usermod >/dev/null 2>&1 && [[ -n "${SUDO_USER:-}" ]]; then
    usermod -aG docker "${SUDO_USER}" 2>/dev/null || true
  elif command -v sudo >/dev/null 2>&1; then
    sudo usermod -aG docker "${USER}" 2>/dev/null || true
  fi

  if docker ps >/dev/null 2>&1; then
    log "Docker 安装完成且可正常使用。"
    return 0
  fi

  log "Docker 已安装，但当前用户暂时无法访问 docker。"
  log "请重新登录，或运行：newgrp docker"
  return 1
}

ensure_docker() {
  if docker_available; then
    return 0
  fi
  if [[ "${NO_INSTALL_DOCKER}" == "1" ]]; then
    fail "Docker 不可用，且已禁用自动安装。请手动安装 Docker。"
  fi
  if install_docker_linux; then
    if docker_available; then
      return 0
    fi
  fi
  fail "Docker 仍不可用。请手动安装并启动 Docker 服务。"
}

wait_tcp() {
  local name="$1"
  local host="$2"
  local port="$3"
  local attempts="${4:-60}"
  local index=1
  while (( index <= attempts )); do
    if timeout 1 bash -c ":</dev/tcp/${host}/${port}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    index=$((index + 1))
  done
  echo "${name} did not become reachable at ${host}:${port}" >&2
  return 1
}

ensure_test_database() {
  compose_cmd exec -T postgres psql -U blank -d postgres -tc "select 1 from pg_database where datname = 'blank_test'" \
    | grep -q 1 || compose_cmd exec -T postgres createdb -U blank blank_test
}

args=("$@")
command=""
for arg in "${args[@]}"; do
  case "${arg}" in
    --no-install-docker)
      NO_INSTALL_DOCKER=1
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: ${arg}" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -z "${command}" ]]; then
        command="${arg}"
      else
        echo "Unknown argument: ${arg}" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

case "${command}" in
  up)
    ensure_docker
    compose_cmd up -d
    wait_tcp "PostgreSQL" 127.0.0.1 5432 60
    wait_tcp "Redis" 127.0.0.1 6379 60
    wait_tcp "Neo4j" 127.0.0.1 7687 90
    ensure_test_database
    echo "Blank infrastructure is ready:"
    echo "  BLANK_DATABASE_URL=postgresql://blank:blank@127.0.0.1:5432/blank"
    echo "  BLANK_TEST_DATABASE_URL=postgresql://blank:blank@127.0.0.1:5432/blank_test"
    echo "  BLANK_REDIS_URL=redis://127.0.0.1:6379/0"
    echo "  BLANK_TEST_REDIS_URL=redis://127.0.0.1:6379/15"
    echo "  BLANK_NEO4J_URI=bolt://127.0.0.1:7687"
    ;;
  down)
    compose_cmd down
    ;;
  status)
    ensure_docker
    compose_cmd ps
    ;;
  logs)
    ensure_docker
    compose_cmd logs -f
    ;;
  "")
    usage
    ;;
  *)
    echo "Unknown command: ${command}" >&2
    usage >&2
    exit 2
    ;;
esac
