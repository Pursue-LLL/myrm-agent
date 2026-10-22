# Bounded Stderr Diagnostic Surface & Actionable Error UX Suite Architecture

## 1. 业务痛点与第一性原理
彻底终结子进程/沙箱崩溃时仅报冷冰冰的 Exit Code 1 / 137、无诊断线索甚至向 UI 泄露未脱敏敏感栈轨迹的恶劣体验。对标 Cherry Studio PR #20042 生产级客户端排障架构实践。

## 2. 核心架构设计
1. **受限内存环形缓冲区（Bounded Stderr Tail Buffer）**：
   - `stderrClassifier.ts` (`appendBoundedStderr`)
   - 限制最大 2 KiB (2048 字节) 内存环形缓冲区捕获终端最后 stderr 尾部，防止大输出导致的内存泄漏与卡顿。
2. **敏感信息脱敏过滤器（Sanitizer）**：
   - `stderrClassifier.ts` (`sanitizeStderrSnippet`)
   - 自动正则替换系统用户主目录（`/Users/xxx/`、`C:\Users\xxx\`）、API 密钥（`sk-xxx`）与 Bearer 令牌，确保原始机密不序列化到渲染器或业务日志。
3. **进程退出因果分类器（Cause Classifier）**：
   - `stderrClassifier.ts` (`classifyStderr`)
   - 覆盖 6 大核心异常分类：`oom_killed` (内存耗尽/Exit Code 137)、`missing_dependency` (缺失运行依赖库)、`port_conflict` (端口冲突 EADDRINUSE)、`auth_invalid` (401 鉴权失效/密钥过期)、`permission_denied` (系统权限不足 EACCES)、`network_timeout` (连接拒绝或超时)。
4. **可操作排障向导卡片（Actionable Diagnostic Surface）**：
   - `ActionableDiagnosticSurfaceCard.tsx`
   - 拒绝死胡同：为每类错误装配直观的人话根因解读与一键排障操作按钮（如“一键在沙箱安装 xxx”、“将沙箱内存提升至 4GB”、“自动分配可用端口”）。
5. **状态管理引擎（Stderr Diagnostic Store）**：
   - `useStderrDiagnosticStore.ts`
   - 管理环形流式追加、分类派发与一键修复动作执行反馈。

## 3. 质量指标与红线
- 单文件全部受控在 180 行以内（远低于 400 行）；
- 严禁 `any` 类型，完整 TypeScript 类型契约；
- 零原生 emoji，全部采用 Lucide 矢量图标；
- 严格遵循语义化 HTML（`<section>`）杜绝 a11y 警告。
