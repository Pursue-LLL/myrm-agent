# Myrm Skill Sandbox

Skill 执行 Docker 沙箱镜像。开发、测试、生产使用同一镜像。

架构与文件清单见 **[_ARCH.md](_ARCH.md)**。

## 快速开始

```bash
cd myrm-agent-server/docker/sandbox

# 单架构（默认 amd64）
./build.sh latest

# 多架构（amd64 + arm64）
./build.sh latest linux/amd64,linux/arm64

# 镜像验证
docker run --rm myrm/skill-sandbox:latest python -c "import pandas; print('ok')"
./deep_health_check.py   # 或容器内 deep-health-check
```

## 要点

- Python 3.14 + Node 20 + Bun；uv + `uv.lock` 锁定依赖
- 非 root、`ReadonlyRootfs`、CapDrop ALL
- 轻量健康检查（60s）+ 深度检查（5min）
- 多架构：PR 单架构，main 双架构

详细运维说明见 `_ARCH.md` 与 `CHANGELOG.md`。
