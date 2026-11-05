# settings/sections/system/stack-update/

## 架构概述

全栈更新状态面板：`index.tsx` 组合状态机与操作，`Changelog` 与 `Snapshots` 是纯展示子面板。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `index.tsx` | 更新状态、OTA 操作、自检与勿扰偏好 |
| `Changelog.tsx` | 分组更新日志与展开/收起 |
| `Snapshots.tsx` | 自动备份开关、立即备份、快照恢复/删除 |
