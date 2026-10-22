# settings/sections/integration/integrations/connect-dialog/ 模块架构

## 架构概述

`IntegrationConnectDialog`（上级目录）的内部分层：探测、安全闸门两个 hook 各持一份状态，探测诊断与认证区两个展示组件只渲染不决策。对话框本体负责 API Key 凭证校验与配置组装，并把它们串联。

## 文件清单

| 文件                        | 职责                                                                                                                                                                                            |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `probe.ts`                  | 探测状态 / 推荐模式 / 原因码枚举及归一化、reasonCode 到文案 key 的映射、探测资格判定与地址解析（纯函数；仅本机回环目标可探测，远端托管条目由安全闸门握手校验；同目录 `probe.test.ts` 覆盖资格与解析） |
| `useConnectivityProbe.ts`   | 连接前的 MCP 端点连通性探测状态机，消费后端 `shouldBlockConnect` / `reasonCode` / `recommendedMode`；`runProbe` 返回是否可继续连接，`reportLocalOnlyBlocked` 不发请求即给出 local-only 阻断诊断 |
| `useCatalogSecurityGate.ts` | 启用前安全闸门、高风险确认挂起态、通过后落库（继承目录条目的 `hostSerial` / `keepaliveInterval`；服务已存在则不重复写入）                                                                       |
| `ProbeDiagnostics.tsx`      | 探测失败态的本地化诊断与推荐动作（重试探测 / 切换到本地模式），无状态                                                                                                                           |
| `AuthSection.tsx`           | 按认证方式渲染认证区：免认证说明 / 单字段与多字段凭证输入，无状态                                                                                                                               |
| `__tests__/`                | 对话框流程特征化测试（API Key、探测、安全闸门含扫描期间按钮忙碌）、闸门落库去重单测 `useCatalogSecurityGate.test.tsx` 与共享测试替身 `connectDialogTestKit.tsx`                                                   |

## 依赖

- [integrations/_ARCH.md](../_ARCH.md)
- `@/lib/api` — 探测的 REST 调用
- `@/hooks/settings/useMcpSecurityGate` — 启用前安全扫描闸门
