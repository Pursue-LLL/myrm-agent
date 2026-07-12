# settings/model-service/

Provider / 模型服务配置 UI：增删 Provider、API Key、批量迁移与硬件 Cookbook。

| 文件 | 职责 |
|------|------|
| `ProviderConfig.tsx` / `AddProviderDialog.tsx` / `DeleteProviderDialog.tsx` | Provider CRUD |
| `ApiKeyManager.tsx` / `ApiUrlSelector.tsx` | 凭证与端点 |
| `ModelCheckbox.tsx` / `ModelInfoCard.tsx` / `InlineModelInfo.tsx` | 模型列表与信息 |
| `AddModelInput.tsx` / `ModelImportDialog.tsx` / `BatchMigrateDialog.tsx` | 模型导入与迁移 |
| `HardwareCookbook.tsx` | 硬件推荐文案 |
