#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${BLANK_IMAGE_OUTPUT_DIR:-${ROOT_DIR}/dist/docker-images}"
BACKEND_IMAGE="${BLANK_BACKEND_IMAGE:-blank-learning/backend:local}"
FRONTEND_IMAGE="${BLANK_FRONTEND_IMAGE:-blank-learning/frontend:local}"
ALL_IN_ONE_IMAGE="${BLANK_ALL_IN_ONE_IMAGE:-blank-learning/all-in-one:local}"
FRONTEND_API_BASE="${VITE_API_BASE_URL:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/build-docker-images.sh [options]

Options:
  --output-dir <dir>          镜像 tar 包输出目录，默认 dist/docker-images
  --frontend-api-base <url>   分离前端镜像的构建期 API 地址，默认使用前端运行时同主机 8000 端口
  -h, --help                  显示本帮助

Environment:
  BLANK_BACKEND_IMAGE         后端镜像名，默认 blank-learning/backend:local
  BLANK_FRONTEND_IMAGE        前端镜像名，默认 blank-learning/frontend:local
  BLANK_ALL_IN_ONE_IMAGE      合并镜像名，默认 blank-learning/all-in-one:local
  BLANK_IMAGE_OUTPUT_DIR      输出目录，默认 dist/docker-images
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --frontend-api-base)
      FRONTEND_API_BASE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "${ROOT_DIR}"
mkdir -p "${OUTPUT_DIR}"

echo "[docker-build] 构建后端镜像：${BACKEND_IMAGE}"
docker build -f docker/backend.Dockerfile -t "${BACKEND_IMAGE}" .

echo "[docker-build] 构建前端镜像：${FRONTEND_IMAGE}"
docker build \
  -f docker/frontend.Dockerfile \
  --build-arg "VITE_API_BASE_URL=${FRONTEND_API_BASE}" \
  -t "${FRONTEND_IMAGE}" .

echo "[docker-build] 构建合并镜像：${ALL_IN_ONE_IMAGE}"
docker build -f docker/all-in-one.Dockerfile -t "${ALL_IN_ONE_IMAGE}" .

backend_tar="${OUTPUT_DIR}/blank-backend-local.tar"
frontend_tar="${OUTPUT_DIR}/blank-frontend-local.tar"
all_in_one_tar="${OUTPUT_DIR}/blank-all-in-one-local.tar"

echo "[docker-build] 导出镜像：${backend_tar}"
docker save -o "${backend_tar}" "${BACKEND_IMAGE}"

echo "[docker-build] 导出镜像：${frontend_tar}"
docker save -o "${frontend_tar}" "${FRONTEND_IMAGE}"

echo "[docker-build] 导出镜像：${all_in_one_tar}"
docker save -o "${all_in_one_tar}" "${ALL_IN_ONE_IMAGE}"

echo "[docker-build] 完成。"
echo "  ${backend_tar}"
echo "  ${frontend_tar}"
echo "  ${all_in_one_tar}"
