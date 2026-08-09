# settings/model-service/

Provider / 模型服务配置 UI：增删 Provider、API Key、批量迁移与硬件 Cookbook。

| 文件 | 职责 |
|------|------|
| `ProviderConfig.tsx` / `AddProviderDialog.tsx` / `DeleteProviderDialog.tsx` | Provider CRUD |
| `ApiKeyManager.tsx` / `ApiUrlSelector.tsx` | 凭证与端点 |
| `ProviderOAuthSection.tsx` | Provider OAuth 订阅登录（PKCE / Device Code） |
| `ModelCheckbox.tsx` / `ModelInfoCard.tsx` / `InlineModelInfo.tsx` | 模型列表与信息 |
| `AddModelInput.tsx` / `ModelImportDialog.tsx` / `BatchMigrateDialog.tsx` | 模型导入与迁移 |
| `HardwareCookbook.tsx` | 硬件推荐文案 |
| `ProviderIcon.tsx` | 内置/自定义 Provider 头像（内置走 LobeHub static SVG 按需加载） |
| `provider-brand-icon-loaders.ts` | 26 个内置 Provider → `@lobehub/icons-static-svg` 动态 import 映射 + 缓存 |
| `__tests__/provider-brand-icon-loaders.test.ts` | 内置 Provider 图标覆盖率 + SVG 文件存在性 + slug/import 对齐测试（`pretest`/`verify:provider-icons` 门禁） |
