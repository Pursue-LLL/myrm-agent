# lib/rendering/

渲染可靠性基础设施。当前承载 React 嵌套更新溢出（#185 / "Maximum update depth
exceeded"）的自愈守卫，供流式高频 store 订阅热路径使用。

## 文件

| 文件                              | 职责                                                                                                                             |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `update-overflow-guard.ts`        | #185 精确识别 + 按源限频 ERROR 日志 + 同源持续振荡熔断（5s→60s 指数退避暂停通知通道）+ 测试缝 reset。除 #185 外任何错误原样 rethrow。 |

## 设计要点

- **为什么不放在 hooks/ 或 components/**：守卫是纯逻辑（无 React 依赖、无 store
  依赖），按仓库分层规范纯逻辑下沉 `@/lib`（见根 `_ARCH.md` 依赖表：lib = 纯函数
  与常量）。hooks 消费它，ErrorBoundary 也消费它。
- **熔断语义**：暂停「store → React 通知通道」而非吞数据。version 单调，退避窗口
  结束后源以一次合并补发 catch-up，数据零丢失。
- **选用准则**：仅对流式高频热路径启用；低频精确状态订阅保留
  `useSyncExternalStore`。

## 消费者

- `@/hooks/shared/useStoreVersion`（热路径通知包装）
- `@/components/error-boundary/GlobalErrorBoundary`（吸收层集成）