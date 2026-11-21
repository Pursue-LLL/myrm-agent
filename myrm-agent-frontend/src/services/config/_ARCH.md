# services/config（前端）

## 架构概述

统一用户配置同步层：`ConfigSyncManager` 为唯一写入网关，Store 为 reactive view。
支持 Tauri（SQLite）与 Sandbox（PostgreSQL + 服务端加密）两种部署模式。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | I/O/P |
| ------------------------------ | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ConfigSyncManager.ts`         | 核心 | 配置的唯一写入网关：乐观更新缓存、防抖 / fast-path 同步、`commitIfDirty`、`ensureKeyLoaded`（渐进加载下读取前确保目标 key 已同步，返回状态是否已知，永不抛出）、`reloadKeys`（后端在页面存活期间改了配置行时换上后端当前值，见 `serverReload.ts`）、迟到记录（后台预加载、`ensureKeyLoaded` 单个 key 的读取）经 `initialLoad.ts` 的 `landLateRecords` 落进缓存空缺并通知订阅者；待写队列及其定时器与联网监听（`outbox.ts`）、冲突消解、首屏与迟到记录加载、本机写入的记录簿记、订阅分发、启动归一化各自落在下面的独立模块里，管理器只持有缓存并调度它们；单例被重置时 `dispose()` 释放写入出口的定时器与监听。**密钥丢失的行不回写**：服务端把「已加密存储但封存它的密钥已丢失」的行标成 `unreadable`（值为空），`commitIfDirty` / 启动归一化对这样的键不回写默认值，只有用户显式保存才覆盖；`getUnreadableKeys()` 列出这些键供横幅提示 | ✅    |
| `outbox.ts`                    | 核心 | 写入出口（`ConfigOutbox`）：持有待写队列与非白名单键的内存队列，承担防抖 / fast-path 发送、可恢复失败后的离线保留、联网重试与启动重放；**同一时刻只有一批在途**：下一批在上一批的答复落地后才生成，带的是那次答复返回的版本，不会与本机上一次写入撞出冲突；**答复只结算它点名的键**：被接受的键落成合并基线并摘除存储里对应的副本（发送期间同键的更新编辑留在队列与存储里），冲突的键交给 `conflictResolution.ts`，答复没点名的键留在队列里；被保留的变更排在同键更新的编辑之前；冲突消解期间（可能在等用户作答）该键的更新编辑排队等待，其余键照常发送；后端没接住的变更留在队列（白名单键同时留在存储）并带退避重试：间隔从 1 秒起每次翻倍、封顶 1 分钟，后端有应答即从头计，`forceSync()` 对这类变更返回失败结果；后端整批拒绝（它先校验整批、不指明是哪一项）时逐键单独重发：被接受的键照常确认，只有被拒的键丢写入，`forceSync()` 仍以整批的拒绝报错；无人等待的发送被后端拒绝时由发送本身记日志，不产生未处理的拒绝；启动与联网重放逐条判断上次会话留下的变更（决策见 `offlineReplay.ts`）：结清的离开存储，读不出服务端状态的原样留着等下一次联网或启动，其余乐观写入缓存后排在队列最前随队列发送，重放期间新做的编辑不受影响，存储里的副本等后端接受后才摘除，队列已持有的同键更新编辑由队列自己发送、不进入重放；管理器的缓存与适配器经 `OutboxHost` 在调用时读取（`initialize()` 会整体替换缓存表）；`dispose()` 释放防抖与重试定时器及 `online` 监听 | ✅    |
| `outboxAnswer.ts`              | 核心 | 后端答复如何落到它所答复的那批变更上（纯函数）：`partitionByAnswer` 把一批变更按答复点名的内容分成被接受（答复成功，或点名了它的版本）、版本冲突、未被点名三类，未被点名的键命运未知、留在队列里；`mergeAnswers` 把逐键单独发送的各个答复合成整批本应收到的那个答复：全部成功才成功，冲突与版本取并集，保留第一条错误 | ✅    |
| `offlineQueue.ts`              | 核心 | 离线队列的浏览器存储：**落盘只收白名单键**，含密钥的键只在内存队列里重试，不写 `localStorage`；队列合并保留最早的基准版本，同 key 的最新值以编辑时间（而非到达顺序）判定；`removeOfflineEntries` 只摘除后端已结算的条目（同 key 更新的编辑与其他 key 保留）；`takeUnpersistableOfflineEntries()` 在管理器启动时（先于后端可达性检查）把存储里已有的非白名单条目移出存储、交给内存等待重放；`isRecoverableSyncError` 识别「没有送达后端」的写入结果                                                                                                                                                                                 | ✅    |
| `offlineReplay.ts`             | 核心 | 离线重放决策（纯函数）：`decideReplay` 对上次会话留下的每条变更单独决定去向——服务端没有该键的行：直接发送（没有可冲突的对象，不问用户）；服务端已是同一个值：视为已到达，不发送；记录的基准版本等于服务端当前版本：发送；服务端已前进（**过期闸门**）：逐条交给冲突解决器由用户决定，没有解决器或解决器失败时服务端值胜出，避免陈旧快照覆盖服务端新配置；读不出服务端状态的键：不下结论，留在原处等待；决策里不编造数据（没有服务端行就不凭空造版本或设备），调用方须先载入队列涉及的 key 并报告读不出的键；`mergeLatestChanges` 每个 key 取最新值，并带上服务端最近确认的版本（没有记录时沿用变更自带的版本）                                                                                                                                                                                                                                        | ✅    |
| `localWrites.ts`               | 核心 | 本机写入的记录簿记（纯函数，缓存经参数传入）：`buildLocalRecord` 造出记录（不带 `unreadable`，用户显式保存即解除「读不出」标记）；`applyReplayedChanges` 把待重放变更里每个 key 的最新值乐观写进缓存并通知订阅者（与 `set()` 同语义，先写缓存再通知）；`recordSyncedChanges` 在后端接受后把已发送的变更落成独立的合并基线拷贝，缓存仍持有该值时同步落成缓存副本（发送期间用户又改过同一个键，缓存保留更新的值，不被旧值盖回） | ✅    |
| `conflictResolution.ts`        | 核心 | 版本冲突分级消解（见下表）与冲突解决器类型；通过 `ConflictContext` 接收管理器的缓存与适配器，自身无状态且不发送：返回待重发的变更（本地值 + 服务端版本）与读不到服务端而未能消解的键，由写入出口重发或放回队列，本地值不丢；key 从未加载（没有基线）时不拿服务端值当基线：服务端独有的字段并入，重叠字段交给解决器，同设备写入的版本也不静默保留；`adoptServerRecord` 把服务端记录同时落到缓存、合并基线与订阅者（`RecordSink`），冲突消解、`landLateRecords`（后台预加载、`ensureKeyLoaded`）、`reloadKeys` 共用这一个落地动作                                                                                                                                                                                                                                                                                                                                                               | ✅    |
| `serverReload.ts`              | 核心 | 后端在页面存活期间改了配置行后的重载（迁移向导写模型槽位 / 已导入密钥 / MCP 服务器 / 全局指令；插件导入与卸载写 MCP 服务器）：按 key 取后端当前记录并 `adoptServerRecord`，缓存、合并基线、订阅者一起前进，下一次保存带的是后端的版本而不是旧基线；**本地有尚未同步改动的 key（缓存值与合并基线不同）保留不动**，交给常规同步对账；读取进行期间被本地写入过的 key 同样保留（应答早于那次写入）；缓存已是后端版本的 key 不重复通知；读取失败整体抛出、缓存不动；自身无状态，缓存经 `RecordSink` 传入 | ✅    |
| `initialLoad.ts`               | 核心 | 首屏加载：最多尝试 3 次；Sandbox 模式先取核心 key、其余以延迟启动的 thunk（同样最多尝试 3 次）交还管理器后台预加载，本地模式一次取全；`landLateRecords` 把迟到记录落进缓存空缺（缓存已有的 key 保留：迟到的答复可能比用户期间保存的值更旧），经 `adoptServerRecord` 一起进缓存、基线拷贝并通知订阅者                                                                                                                                                                                                                                                                                                                                                                                          | ✅    |
| `configListeners.ts`           | 辅助 | 按 key 的订阅者注册表，单个订阅者抛错不影响其余订阅者                                                                                                                                                                                                                                                                                                                                                                                                                                                     | ✅    |
| `startupNormalization.ts`      | 辅助 | 启动归一化遍历（Web Lock 内），写入走管理器的 `commitIfDirty`，因此不会覆盖读不出的密文行                                                                                                                                                                                                                                                                                                                                                                                                                 | ✅    |
| `e2eSearchSyncGate.ts`         | 辅助 | E2E 测试开关：E2E 运行里搜索配置只留在本地，不进同步队列也不通知订阅者；未设置标志时为空操作，生产构建从不读标志                                                                                                                                                                                                                                                                                                                                                                                                              | ✅    |
| `offlinePersistableKeys.ts`    | 核心 | 离线队列允许明文落盘的配置键白名单（仅服务端也不加密存储的键）。白名单而非黑名单：新增键默认不落盘；服务端 `tests/architecture/test_offline_persistable_keys_parity.py` 保证它恰好等于前端全部配置键减去 `SENSITIVE_CONFIG_KEYS`                                                                                                                                                                                                                                                                          | ✅    |
| `configNormalizer.ts`          | 核心 | 启动归一化管道（providers / personalSettings）；`dropNullFields`：服务端会把未设置的字段存成 null，归一化与 `useConfigStore` 订阅都把 null 当作未设置而保留默认值（否则列表型默认字段变 null，设置页读 `.length` 崩溃）                                                                                                                                                                                                                                                                                   | ✅    |
| `configFingerprint.ts`         | 辅助 | 稳定 fingerprint / deep equal，跳过 no-op 写入                                                                                                                                                                                                                                                                                                                                                                                                                                                            | ✅    |
| `themePersonalSettingsSync.ts` | 辅助 | 检测 personalSettings 主题字段变更，触发 ConfigSync fast-path                                                                                                                                                                                                                                                                                                                                                                                                                                             | ✅    |
| `configInitLock.ts`            | 辅助 | Web Locks API，单 tab 执行启动迁移写                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | ✅    |
| `mergeUtils.ts`                | 辅助 | 三向深度合并                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | ✅    |
| `types.ts`                     | 核心 | ConfigKey 枚举、默认值、版本号工具                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | ✅    |
| `adapters/TauriAdapter.ts`     | 适配 | 本地 HTTP → SQLite；后端不可用时读取抛错、写入返回失败结果（约定见 `adapters/_ARCH.md`）                                                                                                                                                                                                                                                                                                                                                                                                                  | ✅    |
| `adapters/SandboxAdapter.ts`   | 适配 | 云端 API → PostgreSQL；只有 404 答「没有这一行」，其余读取失败抛错；没送达的写入返回失败结果，被后端拒绝的写入抛错                                                                                                                                                                                                                                                                                                                                                                                        | ✅    |
| `adapters/BaseAdapter.ts`      | 适配 | deviceId、版本号基类；两个适配器共用的「后端不可用」写入失败结果与传输失败判定                                                                                                                                                                                                                                                                                                                                                                                                                            | ✅    |
| `index.ts`                     | 核心 | ConfigSync 公共 API barrel（`@/services/config`）                                                                                                                                                                                                                                                                                                                                                                                                                                                         | ✅    |

## 内置 provider 合并

`configNormalizer.ts` 的 `BUILT_IN_FIELD_OWNER` 为 `ProviderConfig` 的每个字段声明归属（出厂定义 / 用户保存值），类型上对全部字段穷举，新增字段时编译期强制作出决定；`mergeBuiltInProvider` 据此保留用户字段（启用状态、密钥、基址、模型选择、密钥池策略、订阅登录标志 `oauthConnected`、出口代理），其余取出厂定义。漏掉的字段会在每次启动被重置为出厂值。

## 主题持久化 fast-path

`personalSettings` 内 `activeThemeProfileId` / `themeProfiles` / `themeFontOverride` 变更时：

1. `ConfigOutbox.enqueue(change, true)` 先 `saveOfflineQueue` — 关 tab 前落盘待同步队列
2. 跳过 1s debounce，立即发送

`securityConfig` 同样走 fast-path：安全关键变更（如 YOLO 关闭）立即持久化，避免
1s debounce 内关 tab/刷新丢失，造成「UI 显示已关闭但后端仍开启」的安全假象。

非主题字段仍走常规 debounce。见 `themePersonalSettingsSync.ts` + `ConfigSyncManager.set()`.

## 渐进加载与订阅通知

Sandbox 模式下 `initialize()` 只 await 核心 key（providers/chatSettings/personalSettings），
其余 key（含 `securityConfig`）后台异步预加载（最多尝试 3 次）。预加载写入缓存时**同步通知订阅者**——
否则「配置就绪后兜底」类逻辑（如 securityConfig ⇄ YOLO 互斥重放）永远收不到触发。缓存里已有的 key 不被迟到的答复覆盖（用户在读取进行中保存的值、先到的同 key 答复都保留），迟到的答复只补空缺。
读取即决策的路径（安全预设、本地模型密钥、发送前的搜索服务检查、离线队列重放前的比对）应使用 `ensureKeyLoaded(key)` 显式等待目标 key 同步；它返回状态是否已知（缓存命中，或服务端已答复，含「没有这一行」为 true；请求失败为 false，永不抛出），状态未知时的去向由调用方决定，需要等待上限时配合 `@/lib/utils/withTimeout`。

## 后端写入后的重载

同步层不轮询、不订阅后端：配置在启动时读入（Sandbox 模式渐进加载），之后只在自己的写入遇到版本冲突或调用方要求重载时才重读该 key。页面存活期间若后端自己写了配置（迁移向导写模型槽位、已导入的密钥、MCP 服务器与全局指令；
插件导入与卸载写 MCP 服务器），缓存会落后：设置页继续显示旧值，下一次保存带着旧基线与后端版本冲突——
`providers` / `mcpServers` 这类列表只能整体取舍，可能覆盖刚导入的密钥或连接器。写入方在后端完成后调用 `getConfigSyncManager().reloadKeys(keys)`：
迁移向导与命令中心的导入回滚经 `@/services/memory/migratedConfigReload` 重载 `providers` / `mcpServers` / `personalSettings`；
插件导入与卸载经 `@/components/features/plugins/reloadPluginMcpServers` 重载 `mcpServers`。
本地尚未同步的改动不被覆盖，仍由常规同步对账（见 `serverReload.ts`）。

## 写入一致性（offline replay）

重放判定前，对队列涉及的每个 key 先 `ensureKeyLoaded`：渐进加载下缓存只含核心 key，缓存里没有的 key 无从比对服务端版本，会被判成「服务端已前进」，向用户弹出没有对比数据的冲突框，选「采用服务端」还会丢掉本地编辑。读不出服务端状态的 key（`ensureKeyLoaded` 返回 false）既不比对也不丢弃，留在存储里等下一次联网或启动。联网事件触发的重放先 `initialize()`：启动失败过则重新启动（它自己载入并重放队列），仍不可达就保留队列等下一次联网，不拿空缓存去比对。

冲突解决器先于数据库就绪门装上（`settings-sync-bootstrap.ts`）：别的入口（如 `ensureKeyLoaded`）可能在数据库就绪前就启动同步并重放，那时没有解决器，过期变更只能静默以服务端值为准，用户的离线编辑无从取舍。

- `initialize()` 重放 offline queue **前**：`localWrites.ts` 的 `applyReplayedChanges` 乐观写入 cache 并通知订阅者（与 `set()` 同语义）；需要发送的变更排在写入队列最前，与重放期间新做的编辑一起随队列发送
- 后端接受 **后**：`recordSyncedChanges` 把已发送变更的 `value` 落成 `baseCache`；`cache` 仍是该值（或没有该 key）时同步落成 `cache`，发送期间又改过同一个键则 `cache` 保留更新的值；存储里的副本此时才摘除

保证 `initConfig` 读到的 `personalSettings` 与最后一次本地写入一致，reload 不闪回旧肤。

## 冲突消解分级

| Tier | 条件                   | 行为                   |
| ---- | ---------------------- | ---------------------- |
| T0   | fingerprint 相同       | 不写入                 |
| T1   | 三向合并成功           | 静默合并               |
| T2   | 同 `deviceId` 版本冲突，且有基线 | 静默保留本地           |
| T3   | 写入方 `deviceId` 与本设备不同（另一台设备，或服务端自己写入的行）的同字段冲突；或没有基线时的同字段冲突 | `ConfigConflictDialog`（只能二选一，多个冲突排队逐个作答） |

没有基线指该 key 在本机从未加载（例如后台预加载失败后用户先改了它）：此时服务端独有的字段并入本地值，重叠字段无论由谁写入都走 T3。

## 依赖

- `@/store/config/*` — 类型与迁移函数（providerIdentityMigration）
- `@/components/features/app-shell/settings-sync-initializer.tsx` — 应用顶层初始化（启动序列在 `settings-sync-bootstrap.ts`）
- `@/components/features/app-shell/ConfigConflictDialog.tsx` — T3 冲突 UI
