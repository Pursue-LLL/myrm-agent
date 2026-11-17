# MyrmAgent Frontend

> MIT · Next.js WebUI，对接 `myrm-agent-server`。

包级与分形文档见 **[_ARCH.md](_ARCH.md)**；组件 **[src/components/_ARCH.md](src/components/_ARCH.md)** · Hooks **[src/hooks/_ARCH.md](src/hooks/_ARCH.md)** · 状态 **[src/store/_ARCH.md](src/store/_ARCH.md)**。

## 快速开始

```bash
cd myrm-agent-frontend
bun install
bun run dev    # http://localhost:3000
```

环境变量见 `.env.local`（`API_HOST` / `API_PORT` 决定 `/api/v1/*` 与 `/webui/*` 代理到哪个后端，默认 `127.0.0.1:8080`）。

## 测试

```bash
bun run test              # Vitest（colocated __tests__ + src/__tests__ 集成）
bun run verify:i18n       # 国际化校验
# WebUI E2E：MCP chrome-devtools（真实 Chrome :3000）；禁止 @playwright/test / puppeteer 无头浏览器
```

## 许可证

MIT
