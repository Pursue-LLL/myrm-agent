
# docker/sandbox 模块架构

Skill 执行沙箱 Docker 镜像。Python 3.14 + Node 20 + Bun；uv + `uv.lock` 锁定依赖；非 root、ReadonlyRootfs、CapDrop ALL。

## 构建与验证

```bash
./build.sh latest                          # 单架构 amd64
./build.sh latest linux/amd64,linux/arm64  # 多架构
docker run --rm myrm/skill-sandbox:latest python -c "import pandas"
./deep_health_check.py
```

- PR：单架构快速构建；main：amd64 + arm64
- 轻量 healthcheck 60s；深度检查 5min（pandas/numpy/pdfplumber 等）
- CJK：Noto CJK + `matplotlibrc`；`MPLCONFIGDIR` 指向可写 tmpfs

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `Dockerfile` | 核心 | 多阶段镜像构建定义 |
| `matplotlibrc` | 核心 | matplotlib CJK 默认字体配置 |
| `pyproject.toml` | 核心 | Python 沙箱依赖声明 |
| `uv.lock` | 核心 | 依赖锁文件（确定性构建） |
| `build.sh` | 辅助 | 构建脚本（支持单/多架构） |
| `benchmark.sh` | 辅助 | 性能基准测试脚本 |
| `deep_health_check.py` | 辅助 | 深度健康检查 |
| `test_image.py` | 辅助 | 镜像集成测试 |
| `CHANGELOG.md` | 文档 | 版本更新日志 |
| `README.md` | 文档 | GitHub 入口快速开始 |
