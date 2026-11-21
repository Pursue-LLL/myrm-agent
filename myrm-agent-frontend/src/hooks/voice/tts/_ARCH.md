# hooks/voice/tts/

TTS 输出门面 [`../useTTS.ts`](../useTTS.ts) 的内部模块：浏览器 SpeechSynthesis 引擎、后端 API 引擎与两者共用的类型。门面是唯一对外入口，这里的模块只被它引用。

## 文件清单

| 文件               | 职责                                                                                                                                                                                                                         |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`         | 播放状态 `TTSState`、引擎选择 `TTSMode`、两个引擎共用的 `UseTTSOptions` / `UseTTSReturn`；`TTSMode` 由 `useTTS.ts` 重新导出                                                                                                  |
| `useBrowserTTS.ts` | 浏览器引擎：`window.speechSynthesis` 朗读去掉 markdown 的文本，`speak` 取代正在进行的朗读（去掉 markdown 后没有内容则不动朗读队列）；朗读队列是整页共享的，实例只在持有当前那段话时才取消队列（`stop`、卸载、`speak`）、才响应其事件，没在朗读的消息行不会打断别的行；浏览器不支持时所有控制都是空操作；回归 `../__tests__/useBrowserTTS.test.ts` |
| `useApiTTS.ts`     | API 引擎：`/tts/synthesize-stream` 边收边播（MediaSource），浏览器的 MediaSource 不支持 MP3 时退回一次性取回的 `/tts/synthesize`；合成失败用 toast 提示（503 提示服务端未启用 Edge TTS，其余提示朗读失败）；停止时中止请求并释放音频与对象 URL |

## 依赖

- `@/lib/api`（`getApiUrl`）、`@/lib/utils/toast`、`@/lib/utils/messageUtils`（`stripMarkdown`）
- 父模块 [`../_ARCH.md`](../_ARCH.md)

## 约束

- 只被 `../useTTS.ts` 引用；域外消费者经 `@/hooks/voice/useTTS` 取 `useTTS` 与 `TTSMode`，不直接引用本目录
- 共享类型独立成 `types.ts`：引擎文件不能反向 import 门面（`import/no-cycle`）
- 门面每次渲染都调用两个引擎 hook（hook 顺序固定），按 `mode` 返回其中一个
