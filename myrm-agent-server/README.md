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

## 测试

```bash
cd myrm-agent-server && .venv/bin/python -m pytest
```

## 许可证

MIT — 见 [LICENSE](LICENSE)
