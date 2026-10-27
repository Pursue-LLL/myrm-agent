# remote-backup/

## 架构概述

记忆云端备份卡片（设置 → 记忆 → 云端同步，`/settings/memory?sub=cloud-backup`）的实现；`../RemoteBackupSection.tsx` 只做两张卡片的布局编排，本目录持有状态、网络调用与各块界面。

按「状态 → 接口 → 呈现」分层：`useRemoteBackup.ts` 是唯一持有状态的地方（正在编辑的设置、云端列表、计划任务状态与各动作），`remoteBackupApi.ts` 是唯一与服务端对话的地方，其余组件只吃 props。几条贯穿的约束：

- 列表有自己的状态（`idle / loading / ready / error`）：读不出来的存储显示为「读不出来」并给重试，绝不显示成「没有备份」；先发出的请求晚到，不会覆盖后发出的结果。
- 失败只显示本地化文案：手动备份与计划任务都按服务端稳定的 `error_code`（`config / snapshot / upload / busy / internal`）取文案，不展示服务端措辞；不认识的码按 `internal` 处理。
- 计划频率只提供服务端守得住的四档（60 / 360 / 720 / 1440 分钟，服务端每小时检查一次），保存过的其他数字就近归到其中一档；保留份数同理，已保存的数值不会从选项里消失。
- 手动备份与恢复搬运的是整份快照，服务端自己重试上传，客户端不设超时；其余请求沿用统一入口 `fetchWithTimeout` 的默认超时。
- 备份只覆盖默认智能体与全局共享的记忆，文件是未加密的普通文件，卡片底部的两条说明始终可见；轮转只删除本应用自己更早的备份，不碰其他设备的。

## 文件清单

| 文件                         | 角色 | 职责                                                                                                                                       | I/O/P |
| ---------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `useRemoteBackup.ts`         | 核心 | 状态机：设置读取与编辑、列表（含读取失败状态与过期应答丢弃）、计划任务状态、测试连接 / 保存 / 立即备份 / 恢复 / 删除，所有失败走本地化提示 | ✅    |
| `remoteBackupApi.ts`         | 核心 | `/memory/backup/remote/*` 的类型化调用与失败码映射（`errorCodeKey`）；列表读不出来时抛错，备份失败只返回稳定错误码                         | ✅    |
| `remoteBackupConfig.ts`      | 辅助 | 默认设置、计划频率与保留份数的可选值、已保存设置的归一（`withDefaults` / `snapInterval` / `clampKeep`）、连接信息是否填写                  | ✅    |
| `backupFileName.ts`          | 辅助 | 从备份文件名读出来源设备，列表据此区分多台电脑；不符合命名的文件没有设备                                                                   | ✅    |
| `RemoteConnectionFields.tsx` | 组件 | 存储类型与连接信息（WebDAV / S3 兼容）；密码与密钥字段不触发浏览器自动填充登录密码                                                         | ✅    |
| `RemoteSchedulePanel.tsx`    | 组件 | 自动备份开关与「仅在应用运行时执行」的说明、频率、保留份数及其删除旧备份的提示、设备名                                                     | ✅    |
| `RemoteBackupStatus.tsx`     | 组件 | 最近一次完成的备份，以及计划任务连续失败时的本地化原因（计划关闭时不显示失败）                                                             | ✅    |
| `RemoteFileList.tsx`         | 组件 | 云端备份列表：读取中 / 读取失败 + 重试 / 空 / 列表四种状态，恢复与删除各有确认框并说明后果（恢复只合并不删除，删除不可撤销）               | ✅    |
| `TextField.tsx`              | 组件 | 带标签与说明的单行输入，标签与输入框、说明与输入框都互相绑定                                                                               | ✅    |

## 依赖边界

- 只依赖 `@/lib/*`、`@/services/config` 与 `@/components/primitives/*`；不反向依赖 Settings 容器。
- 连续失败的全局提示不在本目录：由服务端的 `health_alert`（`component=remote_memory_backup`）触发，见 `hooks/globalEvents/backupAlertToast.ts`，落点即本卡片。
- 文案命名空间为 `settings.remoteBackup`（六语言 monolith `locales/*.json`）。
