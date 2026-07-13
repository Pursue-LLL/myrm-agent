# settings/model-service/

Provider / 模型服务配置 UI：增删 Provider、API Key、批量迁移与硬件 Cookbook。

| 文件 | 职责 |
|------|------|
| `ProviderConfig.tsx` / `AddProviderDialog.tsx` / `DeleteProviderDialog.tsx` | Provider CRUD |
| `ApiKeyManager.tsx` / `ApiUrlSelector.tsx` | 凭证与端点 |
| `ModelCheckbox.tsx` / `ModelInfoCard.tsx` / `InlineModelInfo.tsx` | 模型列表与信息 |
| `AddModelInput.tsx` / `ModelImportDialog.tsx` / `BatchMigrateDialog.tsx` | 模型导入与迁移 |
| `HardwareCookbook.tsx` | 硬件推荐文案 |
| `ProviderIcon.tsx` | 内置/自定义 Provider 头像（内置走本地 SVG） |
| `llm-provider-icons.tsx` | 26 个内置 Provider 品牌 SVG 映射 |
| `__tests__/llm-provider-icons.test.ts` | 内置 Provider 图标覆盖率测试 |
