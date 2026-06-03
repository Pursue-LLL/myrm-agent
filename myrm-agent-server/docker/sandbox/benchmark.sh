#!/bin/bash
# 性能基准测试脚本
# 测量镜像大小、构建时间、启动时间等关键指标

set -e

IMAGE_NAME="${1:-myrm/skill-sandbox:latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_FILE="${SCRIPT_DIR}/benchmark-report.txt"

echo "==================================================="
echo "Sandbox Image Performance Benchmark"
echo "==================================================="
echo "Image: ${IMAGE_NAME}"
echo "Date: $(date -Iseconds)"
echo "Host: $(uname -s) $(uname -m)"
echo ""

# 1. 镜像大小
echo "📦 Image Size"
IMAGE_SIZE=$(docker images "${IMAGE_NAME}" --format '{{.Size}}')
IMAGE_SIZE_BYTES=$(docker inspect "${IMAGE_NAME}" --format='{{.Size}}')
echo "   Size: ${IMAGE_SIZE} (${IMAGE_SIZE_BYTES} bytes)"
echo ""

# 2. 镜像层数
echo "📚 Image Layers"
LAYER_COUNT=$(docker history "${IMAGE_NAME}" --no-trunc --format '{{.CreatedBy}}' | wc -l)
echo "   Layers: ${LAYER_COUNT}"
echo ""

# 3. 启动时间测试（5次取平均）
echo "⚡ Startup Time (5 runs)"
TOTAL_TIME=0
for i in {1..5}; do
    START=$(date +%s%N)
    docker run --rm "${IMAGE_NAME}" python -c "print('ready')" > /dev/null
    END=$(date +%s%N)
    RUN_TIME=$(( (END - START) / 1000000 ))  # 转换为毫秒
    echo "   Run $i: ${RUN_TIME}ms"
    TOTAL_TIME=$((TOTAL_TIME + RUN_TIME))
done
AVG_TIME=$((TOTAL_TIME / 5))
echo "   Average: ${AVG_TIME}ms"
echo ""

# 4. 关键包导入时间
echo "📚 Import Time Test"
docker run --rm "${IMAGE_NAME}" python -c "
import time
import sys

packages = ['pandas', 'numpy', 'matplotlib', 'openpyxl', 'playwright']
for pkg in packages:
    start = time.time()
    __import__(pkg)
    elapsed = (time.time() - start) * 1000
    print(f'   {pkg}: {elapsed:.1f}ms')
"
echo ""

# 5. 内存占用测试
echo "💾 Memory Usage Test"
CONTAINER_ID=$(docker run -d "${IMAGE_NAME}" sleep 30)
sleep 2
MEMORY_USAGE=$(docker stats --no-stream --format "{{.MemUsage}}" "${CONTAINER_ID}")
echo "   Idle memory: ${MEMORY_USAGE}"
docker rm -f "${CONTAINER_ID}" > /dev/null
echo ""

# 6. 健康检查测试
echo "🏥 Health Check Test"
CONTAINER_ID=$(docker run -d "${IMAGE_NAME}" sleep 60)
sleep 5
HEALTH_STATUS=$(docker inspect "${CONTAINER_ID}" --format='{{.State.Health.Status}}')
echo "   Health status: ${HEALTH_STATUS}"
docker rm -f "${CONTAINER_ID}" > /dev/null
echo ""

# 7. 生成报告
echo "==================================================="
echo "Benchmark Summary"
echo "==================================================="
{
    echo "Image: ${IMAGE_NAME}"
    echo "Date: $(date -Iseconds)"
    echo ""
    echo "Metrics:"
    echo "- Image Size: ${IMAGE_SIZE} (${IMAGE_SIZE_BYTES} bytes)"
    echo "- Layers: ${LAYER_COUNT}"
    echo "- Avg Startup Time: ${AVG_TIME}ms"
    echo ""
} > "${REPORT_FILE}"

echo "✅ Report saved to ${REPORT_FILE}"
