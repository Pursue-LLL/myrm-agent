# core/storage 模块架构


---

## 架构概述

文件存储服务。提供文件的增删改查功能。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | ✅ 核心 | 文件服务，提供文件 CRUD 功能；`upload_file` 可带 `source_chat_id`，把上传绑定到一个会话 |
| `file_reference.py` | ✅ 辅助 | 本地文件引用的登记辅助：`read_file_reference`（读某个位置已有的记录，缺失或损坏都当作没有）、`file_reference_lock`（同一个文件的登记串行，读与写在同一把锁里） |
| `chat_bound.py` | ✅ 核心 | 绑定到会话的上传：`chat_bound_uploads` / `derivatives_of`（纯函数，导出读 sidecar、保留任务列出文件，用同一套选择规则）、`pdf_extract_source`（PDF 页图的来源标记，唯一拼写处）、`delete_uploads_with_derivatives`（连同页图一起删除，单个文件失败只记日志、不阻断其余） |
| `models.py` | ✅ 辅助 | 存储相关数据模型定义 |
| `paths.py` | ✅ 核心 | 业务存储键约定：文件 / 技能 / 用户配置的键生成函数（`files/{purpose}/…`、`skills/{type}/…`、`config/{name}.json`） |
| `types.py` | ✅ 核心 | 键约定词汇：`FilePurpose`、`SkillType` 枚举（文件与技能服务共用的 SSOT） |

---

## 存储键约定

`paths.py` 生成的键都是 `StorageProvider` 根目录（`{MYRM_DATA_DIR}/storage`）下的相对路径：

```
files/
├── uploads/{file_id}            # FilePurpose.UPLOAD：用户上传
├── generated/{file_id}          # FilePurpose.GENERATED：技能生成
└── skill/{file_id}              # FilePurpose.SKILL：技能包文件
skills/
├── prebuilt/{skill_id}/         # SkillType.PREBUILT：系统预构建技能（含 SKILL.md、_metadata.json）
├── local/{skill_id}/            # SkillType.LOCAL：用户配置路径下扫描到的文件系统技能
└── workspace/{skill_id}/        # SkillType.WORKSPACE：工作目录下发现的项目级技能
config/
└── skills.json                  # 用户技能配置
```

文件元数据位于 `{file_key}.meta.json`。键前缀只决定子目录，存储根仅由 `MYRM_DATA_DIR` 决定。

### 本地文件引用（`sandboxes/`）

本地模式下文件已经在磁盘上，`save_file_reference` 只写一条记录、不上传内容：`sandboxes/{chat_id}/{真实路径去掉根}.meta.json`（`get_file_reference_path`）。记录的位置由（会话, 真实路径）决定，真实路径经 `os.path.realpath` 解析，所以：

- 同一个文件的各种写法（相对、`./`、`..`、符号链接、绝对）落在同一个位置，再次登记读到原记录、沿用原 `id`；这个 `id` 就是工件 `Artifact.id`，按它发布永远是文件当前内容。
- 祖先目录名里带 `workspace/` 的不同文件、不同会话里的同一个文件，位置各不相同，不会被并成一条。
- 键保留完整目录，Windows 盘符的冒号去掉；位置回答的是「这个路径已有 id 吗」，不是「这个 id 对应哪个路径」——记录按 `id` 查不回来（`get_file` 只在 `files/{purpose}/{id}` 下找）。
- 并发登记同一个还没有记录的文件时，读与写在同一把进程内锁里（服务端单进程），只有一个会生成 `id`。记录损坏（写到一半）视为没有，下一次登记覆盖它。

---

## `source_chat_id` 的三种含义

sidecar 里的 `source_chat_id` 按用途有三种取值，消费方不得把它们当成同一种东西：

| 用途 | 取值 | 含义与生命周期 |
|------|------|----------------|
| UPLOAD | 空 | 普通上传，不属于任何会话，保留到用户删除 |
| UPLOAD | 会话 id | 无痕会话的上传（前端只在无痕开启时传 `chat_id`）。仅该会话可在 `@` 建议里看到；会话被清除时一并删除（见下）；不进导出 |
| GENERATED | chat id / `kanban:<task>` / `pdf-extract-<upload id>` | 生成者；7 天过期。`pdf-extract-` 是绑定上传的派生页图，随该上传一起删除、一起排除出导出 |

清除链路：每小时的无痕清理（`services/chat/chat_retention.py`）在删除空闲无痕会话后，立即删除这些会话绑定的上传；另外清扫“会话行不存在且创建超过 24 小时”的绑定上传（会话行随首条回复才写入，从未发送的上传没有会话可随之清除，24 小时宽限避免误删尚未落库的会话）。清扫只看 UPLOAD：GENERATED 的 `source_chat_id` 可以是 `kanban:<task>` 等非会话 id，不能按“会话行是否存在”判断。存储失败只记 warning，剩余文件由下一轮再次选中。

清理的代价：每次运行读取全部 UPLOAD 的 sidecar（本机实测约 0.26 ms/个：201 个 52.6 ms、1001 个 258.8 ms，同一进程内 5 次取最小值；只读 sidecar 不读内容，与文件大小无关），每小时一次，与库里 UPLOAD 总量线性相关。

已知边界：开启无痕之前已上传的文件不绑定，随普通上传保留；PDF 页图仅沙箱/云模式落盘（本机模式内联返回，无文件）。

---

## 依赖关系

- `app/platform_utils/`：`get_storage_provider()` 延迟获取框架存储单例
- `myrm_agent_harness.toolkits.storage`：`StorageProvider` 抽象（与键约定无关）；文件内容与元数据均经它读写，键由本包 `paths.py` 生成
