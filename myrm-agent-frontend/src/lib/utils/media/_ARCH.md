# lib/utils/media/

媒体凭据域子包：媒体 provider 状态映射与图片/TTS/视频凭据就绪判定。**无** React 组件，全部纯函数。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/media`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖凭据就绪判定与 provider 状态映射行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合两文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `mediaCredentialReadiness.ts`：媒体凭据就绪判定 — 图片/TTS/视频三通道凭据就绪判定（isImageMediaCredentialReady / isTtsMediaCredentialReady / isVideoMediaCredentialReady）、凭据警告收集（collectMediaCredentialWarnings）与 provider 活跃 API Key 检测（providerHasActiveApiKey），provider 映射经包内 `mediaProviderStatus.ts`。
- `mediaProviderStatus.ts`：媒体 provider 状态 — resolveImageProviderId provider 归一、VIDEO_PROVIDER_CONFIG_IDS 视频 provider 常量与 fetchMediaProviderStatus 后端状态拉取。

## 依赖

- `@/lib/utils/apiConfig`（POS: API 端点配置）— 后端 URL。
- `@/lib/utils/authHeaders`（POS: 认证头）— 请求认证。
- `@/services/config/types`（POS: 配置服务类型）— VideoGenerationProvider / ImageGenerationConfig / VideoGenerationConfig / VoiceConfigValue 类型。
- `@/store/config/providerTypes`（POS: provider 配置类型）— ProviderConfig 类型。
- `@/store/chat/types`（POS: 聊天类型定义）— BuiltinToolId 类型。
