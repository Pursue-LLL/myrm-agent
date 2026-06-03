# MyrmAgent 前端

> **许可**: **开源**仓库。提供 Web UI 配置与操作界面，对接 `myrm-agent-server` 后端。

MyrmAgent 是一个 Claw-class AI 助手前端应用，提供现代化用户界面与持久化工作空间，支持多 Agent 协作、技能管理与工作自动化。

## 技术栈

- **框架**：Next.js 16 (App Router)
- **UI 库**：React + TypeScript
- **样式**：Tailwind CSS + shadcn/ui
- **状态管理**：Zustand
- **国际化**：next-intl
- **包管理**：Bun

## 功能特点

- 🎨 **现代化 UI**：基于 shadcn/ui 的美观界面设计
- 🏥 **系统诊断**：内置 System Doctor 仪表盘，支持健康指标跟踪与一键修复
- 🌐 **多语言支持**：中英文双语界面
- 🔐 **安全特性**：E2EE 加密敏感配置，OAuth 认证
- 📱 **响应式设计**：完美适配桌面和移动设备
- 🤖 **AI 对话**：支持多种 AI 模型和智能体
- 🧠 **记忆系统**：个性化记忆功能（登录后可用）
- 📚 **知识库**：文档管理和 RAG 检索（登录后可用）
- ⚙️ **技能系统**：MCP 技能扩展支持
- 🔄 **配置同步**：多设备配置同步

## 快速开始

### 环境要求

- Node.js 18+
- Bun (推荐) 或 npm/yarn/pnpm

### 安装依赖

```bash
# 使用 Bun (推荐)
bun install

# 或使用 npm
npm install
```

### 环境配置

创建 `.env.local` 文件：

```env
# 后端 API 地址
NEXT_PUBLIC_API_URL=http://localhost:8080

# 其他配置...
```

### 启动开发服务器

```bash
# 使用 Bun
bun run dev

# 或使用 npm
npm run dev
```

打开 [http://localhost:3000](http://localhost:3000) 查看应用。

## 部署模式

支持三种部署模式（通过环境变量 `NEXT_PUBLIC_DEPLOY_MODE` 配置）：

### Tauri 模式（Desktop/WebUI）

#### Desktop 子模式
- 嵌入式 WebView，无独立 HTTP 服务器
- 自动登录 `local_user`
- 数据存储在本地 SQLite
- 无需网络连接

#### WebUI 子模式
- **双进程架构**：
  - **Next.js Standalone Server**（端口 `webui_port`, 默认 3000）：提供前端静态资源和 API 代理
  - **Python FastAPI**：`run.py --webui` 默认 **25808**；独立 `uv run run.py` 默认 **8080**
- **API 代理**：Next.js `rewrites` 将浏览器侧 `/api/v1/*` 转发到 FastAPI；开发时默认目标是 **8080**，与 `uv run run.py` 一致。若后端为 `--webui`（25808），在前端 `.env.local` 设置 `API_PORT=25808` 并重启 `bun run dev`
- **访问方式**：
  - 本地访问：`http://127.0.0.1:3000`（仅本机）
  - 远程访问：`http://0.0.0.0:3000`（局域网/外网，需启用 `enable_remote_access`）
- **数据和认证**：本地回环访问默认自动登录；开启 **Remote + 需要密码** 时走 `/auth/setup` 自设 admin 密码

### Local 模式（本机 WebUI 开发）

- 与 Tauri 共享本地 SQLite 与 `local_user` API 身份
- `NEXT_PUBLIC_DEPLOY_MODE=local`，API 经 Next rewrites 到 `http://127.0.0.1:8080`（或 `API_PORT`）
- **勿** 使用 `NEXT_PUBLIC_DEPLOY_MODE=sandbox` 联调本地后端，否则会一直跳转「欢迎回来」登录页（CP 认证与 WebUI admin 密码是两套体系）

#### WebUI 认证 E2E（可选）

后端 `uv run run.py` + 前端 `bun run dev` 启动后：

```bash
PLAYWRIGHT_RUN_WEBUI_E2E=1 bunx playwright test tests/e2e/webui-auth.spec.ts
```
- 本机开发勿用 `sandbox` 构建，否则会误走 CP 登录与 Cookie 门禁

### Sandbox 模式（控制平面 + 独立沙箱）

- 仅用于 SaaS/企业：**Google OAuth** 登录（无邮箱注册；旧 `/auth/register`、`/auth/verify-email` 由 Next 重定向到 `/auth/login`），再代理进用户沙箱内的 server
- `NEXT_PUBLIC_DEPLOY_MODE=sandbox`
- 需在控制平面配置 Google OAuth；未配置时登录页显示不可用提示
- 数据存储在云端 PostgreSQL
- 敏感配置使用 E2EE 加密
- 支持多设备同步

> Tauri 和 Local 统称"本地模式"，前端通过 `isLocalMode()` 判断。

### 开发测试

前端支持测试登录功能：

1. 在设置页面点击"本次测试"按钮
2. 或在浏览器控制台执行：
   ```javascript
   localStorage.setItem('auth_token', 'test-user-token-' + Date.now());
   window.location.reload();
   ```

## 项目结构

```
myrm-agent-frontend/
├── locales/                 # next-intl 文案（主维护 zh/en；含 de/ja/ko）
├── public/                  # 静态资源
├── scripts/                 # dev、cleanup、i18n 校验等
├── tests/e2e/               # Playwright E2E
└── src/
    ├── app/                 # App Router 页面与 BFF（api/*）
    ├── components/
    │   ├── layout/          # 应用壳层（侧栏、导航）
    │   ├── primitives/      # shadcn / Radix 基元（button、dialog…）
    │   └── features/        # 业务域模块（chat-window、settings、kanban…）
    │       └── app-shell/   # 全局初始化器、PWA、认证回调等
    ├── hooks/
    ├── i18n/                # next-intl 请求配置
    ├── lib/                 # 工具函数、常量、intent-dispatcher 等
    ├── services/            # 后端 API 客户端（按域单文件导入）
    ├── store/               # Zustand（chat/、config/ 等子目录 + 根级 store）
    ├── types/
    ├── config/
    └── __tests__/           # Vitest
```

> 复杂子模块可含 `_ARCH.md`（如 `features/kanban/`）。

## 开发指南

### 代码规范

- 使用 TypeScript（`strict` 逐步收紧中）
- 遵循 ESLint 配置
- 使用 Prettier 格式化代码
- 组件使用 PascalCase 命名
- 文件使用 kebab-case 命名

### 国际化

项目支持中英文双语，所有用户可见文案都需要：

1. 在 `locales/zh.json` 和 `locales/en.json` 中添加翻译（路径别名 `#locales/*`）
2. 使用 `useTranslations` Hook 获取翻译

```tsx
import { useTranslations } from 'next-intl';

function MyComponent() {
  const t = useTranslations('common');
  return <div>{t('hello')}</div>;
}
```

### 认证状态

前端使用 `isAuthenticated()` 函数检查用户是否已登录：

```tsx
import { isAuthenticated } from '@/lib/guest';

function ProtectedComponent() {
  if (!isAuthenticated()) {
    return <LoginPrompt />;
  }
  return <ProtectedContent />;
}
```

**注意**：本项目不支持访客模式。本地模式（Tauri/Local）自动登录 `local_user`，Sandbox 模式必须 OAuth 登录。

## 构建和部署

### 构建生产版本

```bash
bun run build
```

### 启动生产服务器

```bash
bun run start
```

### 部署到 Vercel

```bash
bun run vercel:deploy
```

## 故障排除

### 常见问题

1. **后端连接失败**
   - 检查后端服务是否运行在 `http://localhost:8080`
   - 检查 CORS 配置

2. **样式不生效**
   - 确保 Tailwind CSS 配置正确
   - 检查 `globals.css` 是否正确导入

3. **国际化不工作**
   - 检查翻译文件语法
   - 确认 `next-intl` 配置正确

## 贡献指南

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证。
