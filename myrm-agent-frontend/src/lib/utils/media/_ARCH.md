# lib/utils/media/

媒体生成设置域子包：图像模型目录、TTS 目录与存储选择映射、媒体 provider 状态映射，以及「Agent 能否用上某个媒体工具」的就绪判定。**无** React 组件，全部纯函数。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/media`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

核心约定：没有隐式默认——用户没选的模型就是「未选择」，服务端不会为它挂载工具；这里的判定与服务端 `app/core/media/selection.py` 同口径。

`__tests__/` 覆盖目录判定、存储选择映射、凭据就绪判定与 provider 状态映射行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合包内公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `imageModels.ts`：图像模型目录 — IMAGE_MODEL_OPTIONS 与生成引擎的模型档案逐项相同（取值由共享契约 `image_models` 约束，服务端测试对照引擎），isImageModelSelected 判定存量选择是否仍在目录内（已下线的模型视为未选）。
- `ttsCatalog.ts`：TTS 目录与选择映射 — TTS_PROVIDER_OPTIONS / TTS_MODEL_OPTIONS / TTS_VOICE_OPTIONS、isTtsSelected（provider、model、voice 都选定才算选定）、readStoredChoices（共享 `voice` 配置 → 当前选择；provider 不在目录内时模型与音色按未选处理）。
- `mediaCredentialReadiness.ts`：媒体工具就绪判定 — imageToolSetup / videoToolSetup / ttsToolSetup 返回 `ready | notSelected | noCredential`，collectMediaCredentialWarnings 汇总为 Agent 配置面板的提示，providerHasActiveApiKey 检测 provider 行是否有生效的 Key；provider 映射经包内 `mediaProviderStatus.ts`。
- `mediaProviderStatus.ts`：媒体 provider 状态 — resolveImageProviderId 由模型取图像 provider，VIDEO_PROVIDER_CONFIG_IDS / videoProviderConfigId 视频 provider 到 provider 表 id 的映射，fetchMediaProviderStatus 后端状态拉取。

## 依赖

- `@/lib/utils/apiConfig`（POS: API 端点配置）— 后端 URL。
- `@/lib/utils/authHeaders`（POS: 认证头）— 请求认证。
- `@/services/config/types`（POS: 配置服务类型）— VideoGenerationProvider / ImageGenerationConfig / VideoGenerationConfig / VoiceConfigValue 类型。
- `@/store/config/providerTypes`（POS: provider 配置类型）— ProviderConfig 类型。
- `@/store/chat/types`（POS: 聊天类型定义）— BuiltinToolId 类型。
