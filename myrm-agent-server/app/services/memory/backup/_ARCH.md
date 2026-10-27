# services/memory/backup 模块架构

## 架构概述

记忆备份与恢复。本地（沙箱持久卷）与远程（WebDAV/S3）两条通道共用同一份**可移植记忆快照**：快照只含记忆内容、不含向量，
恢复时由 `MemoryManager` 重新计算 embedding，因此与 embedding 模型、向量库布局无关。

```
MemoryManager.export_all()/import_memories()      ← 框架提供的可移植导出/导入契约（导出逐页读到末页，读取失败即抛出）
        │
   snapshot.py  ── capture_snapshot（先计数、再导出，数量对不上即失败）
        │        └─ apply_snapshot（replace=清空后回放并校验 / merge=跳过已有内容）
        ├── volume_store.py + service.py   本地备份：创建 / 列表 / 恢复 / 删除
        └── remote_sync/                   远程备份：存储适配（WebDAV/S3）→ 运行器（创建→上传→轮转 / 远程恢复 merge）
                                           → 云端定时备份（按所选间隔运行，记录结果，连续失败只告警一次）
```

数据安全约定：

- 备份要么完整要么不存在：快照捕获发现任一记忆类型导出不全或读取失败就抛 `SnapshotError`，不写文件、不上传。
- 恢复前先解码备份；覆盖式恢复（`overwrite=true`）先把当前记忆另存为一份新备份，再清空回放，回放后逐类型核对数量，失败时提示该备份 id。
- 远程恢复只合并（跳过已有内容），不删除任何已有记忆。
- 备份 id 只接受 `volume_store.py` 生成的格式，路径穿越无从谈起；远程文件名只是存储端选择器，下载总落在固定本地文件名下。
- 远程文件名只有一种写法：`myrm.<UTC 时间戳>.<设备名>.<实例标记>.<平台>.json.gz`。设备名只是给人看的标签：只保留字母、数字、点、短横线与下划线（其余字符、路径分隔符、`#`、`?`、`%` 一律换成短横线，最长 64 个字符），中文等 Unicode 文字原样保留，可以含点（如 `mac.local`）。实例标记说明备份属于谁：取自整实例备份共用的 8 位十六进制标记（`AutoBackupStore.tag()`，一个实例只有一个）。平台与标记都不含点，所以文件名从右往左读：平台在最后，标记在它前面，时间戳与标记之间的全部是设备名。
- 轮转只认写法完全符合上面格式、且带**本实例标记**的文件：刚上传的那份一定保留，其余按名字里的时间戳（取自设备时钟）排新旧，保留最新的 N-1 份（时钟走快过的旧备份名字更靠后，不这样做会在上传成功后立刻把刚上传的删掉）。所以共用同一个文件夹或桶的多个实例（即使设备名、主机名相同）互不裁剪，改设备名后历史仍按同一个标记继续轮转；不带本实例标记的文件（其他程序放进来的、其他实例的）从不被轮转删除，服务端不可靠的列表顺序与修改时间也不会让备份被误删，界面里可以手动删除任何一份。列表读不到（存储端拒绝或传输错误）时跳过轮转：备份已存好，不为清理冒险。WebDAV 列表里的文件名先做百分号解码，与上传时的名字一致；解码后含路径分隔符的条目不是文件夹里的备份，直接跳过。S3 只读取第一页（最多 1000 个对象）。
- 恢复写入必须使用直接写入的 `MemoryManager`（`get_crud_memory_manager`）；走审批队列的管理器会把恢复内容堆进待审批队列，`apply_snapshot` 会直接拒绝。

快照覆盖 `PROFILE / PROCEDURAL / SEMANTIC / EPISODIC`（`SNAPSHOT_MEMORY_TYPES`，与 `MemoryManager.get_enabled_types()` 一致；任务摘要存放在 episodic 集合内随之备份）。
原文对话（CONVERSATION）、派生的 CLAIM/INTEGRATION 既不能被清空也不能在恢复时去重，不属于备份范围。

快照取自备份所用 `MemoryManager` 的默认绑定命名空间，即 `global`（所有智能体共享）与 `agent:default`（默认智能体）（`toolkits/memory/_internal/scope.py::_candidate_namespaces`）；其他命名智能体（`agent:<id>`）、项目（`project:<id>`）与渠道/会话/任务（`channel:`/`conversation:`/`task:`）各自命名空间里的记忆不在其中，界面的备份说明按这一范围写。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `snapshot.py` | 核心 | 可移植记忆快照：`MemorySnapshot` 格式（版本 3，gzip JSON）、`capture_snapshot` 完整性校验捕获、`apply_snapshot` 覆盖/合并回放与回放核对（覆盖只清当前嵌入模型的集合：快照里没有旧模型遗留的记忆，覆盖不能把它们一并销毁）、`encode_snapshot`/`decode_snapshot` | ✅ |
| `volume_store.py` | 核心 | 沙箱持久卷备份库（默认 `~/.myrm/backups/{backup_id}/`）：`save`/`list_backups`/`load`/`delete`；`metadata.json` 最后原子写入，缺它即非完整备份；备份 id 严格校验 | ✅ |
| `service.py` | 核心 | 本地备份编排 `MemoryBackupService`：`create`、`restore`（覆盖式恢复先留底，失败不丢副本） | ✅ |
| `remote_sync/` | 子包 | 远程（云端）备份的全部：存储适配（`storage/`，WebDAV/S3）、运行器（单次备份与远程恢复，远程文件名的唯一写法与轮转规则）、云端定时备份（按用户所选间隔运行，记录每次结果，连续失败只告警一次）。见 [`remote_sync/_ARCH.md`](remote_sync/_ARCH.md) | ✅ |
