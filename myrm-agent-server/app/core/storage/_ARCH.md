# core/storage 模块架构


---

## 架构概述

文件存储服务。提供文件的增删改查功能。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | ✅ 核心 | 文件服务，提供文件 CRUD 功能 |
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

---

---

## 依赖关系

- `app/platform_utils/`：`get_storage_provider()` 延迟获取框架存储单例
- `myrm_agent_harness.toolkits.storage`：`StorageProvider` 抽象（与键约定无关）；文件内容与元数据均经它读写，键由本包 `paths.py` 生成
