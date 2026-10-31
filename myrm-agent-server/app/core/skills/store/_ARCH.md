# skills/store 模块架构


---

## 架构概述

Skill 商店模块。管理 Skill 的 CRUD、用户配置、读取和安全清洗。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域 | 存储层聚合出口：导出 SkillsService / UserSkillConfigManager，并转发 harness 的 `market.sanitizer`（`SKILL_MD_FILE`、`SKILL_NAME_PATTERN`、`sanitize_skill_files`） |
| `service.py` | ✅ 核心 | Skill 商店服务（CRUD、搜索、安装）；`get_skills_by_ids` / `get_user_available_skills` 经 `gates.runtime_load` 排除归档与禁用技能；`find_local_skill_dir` 把一个引用解析成主本地技能目录（`skill_creation_service.base_path`）下的技能目录，`get_local_skill` 取该目录的页面技能：先按目录名找，没有该目录时再按技能的已知名字找（经 `reader.scan_off_loop` 放到扫描线程）。成长审计行与后台复盘结果带的名字不一定是目录名（复盘看到的是智能体运行时的列表名），`/derive`、`/fix` 的引用解析与后台复盘的锁判定共用这一条规则 |
| `local_lookup.py` | ✅ 辅助 | 主本地技能目录里的名字解析（阻塞文件系统调用，不跑安全扫描）：`local_skill_dir_named` 按目录名找（目录名不受技能命名约定限制；空名字、`..`、多于一个路径分量的名字不算目录名，不会走出该目录；没有该目录或没有 SKILL.md、名字长过目录项能有的长度都返回 None，其它文件系统错误原样抛出，因为后台复盘把找不到当作未锁）；`local_skill_dir_listed_as` 按技能的已知名字找（SKILL.md 里的名字，没有则目录名；以及 `normalize_skill_name` 之后智能体运行时列出它用的名字），恰好一个技能叫这个名字才返回，多个不猜；读不了的 SKILL.md 跳过并记警告，主技能目录本身读不了则抛出 |
| `evolution_store.py` | ✅ 辅助 | 进化 SkillStore SQLite 访问（core/services 共用）——进程级单例缓存（`get_evolution_skill_store`），只读调用点不再 close 共享实例；`reset_evolution_skill_store` 供测试隔离；`find_evolution_records` 找出一个技能在进化库里的全部行（按引用精确匹配的行优先，其次 `get_active_skills()` 里记录的 SKILL.md 就在该页面技能目录中的行，不看行的名字，所以改过名的技能保留自己的行、同名而在不同目录的两个技能各用各的行；没有页面技能时按名字取版本号最高的活动行；行键因写入者而异：草稿批准与自动提取在带评测用例时以技能名为键，批量导入以生成的 id 为键、覆盖时沿用被覆盖技能的 id，技能包导入在带评测用例且没有同名行时以导入后的技能 id 为键），供技能页锁开关、`/derive`、`/fix` 使用；`EvolutionRowIndex` 把活动行按其 SKILL.md 所在目录一次索引，技能列表一次请求只建一次，`find_evolution_records` 可复用；`find_primary_evolution_record` 给技能页展示用，与 `/derive`、`/fix` 同一规则取页面技能的首选行（本地技能只按目录，不回退到按名字；非本地技能按名字取版本号最高的活动行）；`evolution_record_for_page_skill` 为没有行的本地页面技能（如对话里创建、手工放置的技能，创建路径不写行）构造以页面 id 为键、内容读自其 SKILL.md 的新行（非本地技能或 SKILL.md 缺失返回 None），由 `/derive`、`/fix` 在确认未被锁之后保存 |
| `reader.py` | ✅ 核心 | Skill 读取器（解析 Skill 包内容）；整盘本地技能扫描会逐个解析 SKILL.md 并跑安全模式（24 个技能约 1 秒，结果不缓存、每次调用重扫），故 `list_local_skills` 与 `SkillsService.get_skill` 经 `scan_off_loop` 交给单线程 worker，事件循环不被冻结；单 worker 因扫描受 GIL 限制，重叠只会互相拖慢 |
| `user_config.py` | ✅ 辅助 | 用户 Skill 配置（个人偏好、启用/禁用） |
