#!/bin/bash
# 构建沙箱 Docker 镜像
# 用法: ./build.sh [TAG] [PLATFORMS]
#   TAG: latest（默认）, v1.0.0 等
#   PLATFORMS: linux/amd64（默认单架构）, linux/amd64,linux/arm64（多架构）
#
# 示例:
#   ./build.sh latest                         # 单架构（amd64）
#   ./build.sh latest linux/amd64,linux/arm64 # 多架构
#
# 统一镜像策略：开发、测试、生产使用同一镜像，确保环境一致性
# 依赖管理：使用 uv + pyproject.toml + uv.lock 确保确定性构建

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="myrm/skill-sandbox"
IMAGE_TAG="${1:-latest}"
PLATFORMS="${2:-linux/amd64}"

echo "🐳 Building sandbox image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "   Package Manager: uv (确定性构建)"
echo "   Features: Python + Node.js + Bun"
echo "   Packages: 70+ Python packages (pyproject.toml)"
echo "   Platforms: ${PLATFORMS}"
echo "   Optimizations: BuildKit cache, multi-stage build, layer optimization"
echo ""

# 检查 uv.lock 是否存在
if [ ! -f "${SCRIPT_DIR}/uv.lock" ]; then
    echo "⚠️  uv.lock not found, generating..."
    (cd "${SCRIPT_DIR}" && uv lock)
fi

# 启用 BuildKit
export DOCKER_BUILDKIT=1

# 记录开始时间
START_TIME=$(date +%s)

# 检测是否为多架构构建
if [[ "${PLATFORMS}" == *","* ]]; then
    echo "🏗️  Multi-architecture build detected, using buildx..."
    
    # 确保 buildx builder 存在
    docker buildx create --use --name sandbox-builder 2>/dev/null || docker buildx use sandbox-builder 2>/dev/null || true
    
    # 多架构构建
    docker buildx build \
        --platform "${PLATFORMS}" \
        --progress=plain \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -f "${SCRIPT_DIR}/Dockerfile" \
        --load \
        "${SCRIPT_DIR}"
else
    echo "🏗️  Single architecture build (${PLATFORMS})..."
    
    # 单架构构建
    docker build \
        --progress=plain \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -f "${SCRIPT_DIR}/Dockerfile" \
        "${SCRIPT_DIR}"
fi

# 记录结束时间并计算耗时
END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

echo ""
echo "✅ Build complete: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "   Build time: ${BUILD_TIME}s"
echo ""

# 显示镜像信息
docker images "${IMAGE_NAME}:${IMAGE_TAG}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# 保存性能数据
echo "${IMAGE_TAG},$(date -Iseconds),${BUILD_TIME}s,$(docker images ${IMAGE_NAME}:${IMAGE_TAG} --format '{{.Size}}')" >> "${SCRIPT_DIR}/.build-metrics.csv"



