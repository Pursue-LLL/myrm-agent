# MyrmAgent Frontend

> MIT · Next.js WebUI，对接 `myrm-agent-server`。

组件与状态架构见 **[src/components/_ARCH.md](src/components/_ARCH.md)** · **[src/store/_ARCH.md](src/store/_ARCH.md)**。

## 快速开始

```bash
cd myrm-agent-frontend
bun install
bun run dev    # http://localhost:3000
```

环境变量见 `.env.local`（`NEXT_PUBLIC_API_URL` 默认代理到 :8080）。

## 测试

```bash
bun run test              # Vitest（src/__tests__、组件单测）
bun run verify:i18n       # 国际化校验
# Playwright E2E：tests/e2e/
```

## 许可证

MIT
