# MyrmAgent Server

> MIT · FastAPI 业务后端，对接 WebUI / Tauri 桌面。

架构与模块说明见 **[ARCHITECTURE.md](ARCHITECTURE.md)** · **[app/_ARCH.md](app/_ARCH.md)**。

## 快速开始

```bash
# 在 myrm-agent 根目录（推荐）
myrm setup
myrm dev      # 仅后端 :8080
myrm start    # 后端 + 前端 → http://localhost:3000

# 或仅 server 目录
cd myrm-agent-server && uv sync --all-extras && .venv/bin/python run.py
```

- API 文档：<http://localhost:8080/docs>
- Harness 来自 PyPI（`uv.lock`），勿 vendoring 源码
- 业务配置通过 WebUI Settings 管理，勿在 `.env` 写 API Key
- 本地搜索配置：`searxng/`（见 [searxng/_ARCH.md](searxng/_ARCH.md)）

## 测试

```bash
cd myrm-agent-server && .venv/bin/python -m pytest
```

## 部署入口

| 路径 | 用途 |
|------|------|
| `deploy.py`（根目录） | 薄 shim → `scripts/deploy.py`；本地/Docker 部署 CLI 入口 |
| `scripts/deploy.py` | 实际部署逻辑 |
| `deployments/` | 可选运维栈配置（如 `deployments/prometheus/` 监控），与 `deploy.py` 无关 |

## 许可证

MIT — 见仓库根目录 [LICENSE](../LICENSE)
