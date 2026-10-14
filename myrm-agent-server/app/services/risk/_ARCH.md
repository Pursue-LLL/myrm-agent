# services/risk 模块架构

## 架构概述

风险管控服务层。提供风险规则管理和实时风险检测能力。

- 检测在事件循环上同步运行，输入是任何聊天发送者可控的文本，所以匹配用 `regex` 包，每条规则对一段文本有 `MATCH_TIMEOUT_SECONDS` 的时间预算；超时的规则按命中处理（宁可拦下，也不放行一条专为拖垮规则构造的消息）。
- 规则的 pattern 先过 harness 的 `pattern_problem`（计数重复展开过大会在编译时吃光内存），再编译；校验、启动加载、规则测试共用 `compile_pattern`，`regex` 默认模式对普通 `re` 写法的含义相同，只在 `[[:alpha:]]` 这类边角写法上不同。
- 动作只有 `block`：不想让一条规则生效就停用它，不再有「放行」这个什么也不改变的选项；启动时把沿用旧 `allow` 的规则改成停用的 block 规则。第一条命中的规则即拦下这段文本。
- 默认启用的只有「安全凭证」分类（`DEFAULT_ENABLED_CATEGORIES`，8 条）：凭证从不需要出现在一条消息里；个人信息、公司、客户、财务法务、政治军事这 23 条是个人助理的日常话题（姓名、邮箱、合同、预算），由用户按自己的数据打开。播种只对新插入的规则套用这一默认，已存在的规则保持用户所设。
- 内置的邮箱、手机号、身份证、银行卡规则直接取隐私检测器（harness `pii_patterns` / `card_context`）的 pattern 源，并在命中后做分类器同样的确认（身份证校验位、示例值排除），渠道闸门与隐私分类器对「什么算个人信息」只有一份定义。
- 凭证赋值类规则（`credential_assignment` / `cookie_session_like` / `env_file_secret`）的 pattern 捕获 `key` 与 `value`，命中后由 harness `secret_value_span` 判断 `value` 是不是真的密钥（调用、标识符、模板、掩码、普通单词都不算），所以粘贴的代码 `password = input()`、`token = os.environ[...]` 不会被拦，`password: Zk9#mango42` 会。`api_key_like` 只匹配以厂商前缀开头的整段 token，不匹配 URL slug 或词尾。
- 纯关键词规则由 `keyword_pattern` 生成：拉丁词按整词匹配（可带复数），`tin` 不会命中 `meeting`，中文词不依赖分词，处处可匹配。
- 命中记录的 `match_summary` 只写位置（`chars:起-止`）或超时标记，不写命中的原文：这些规则要拦的正是密钥与个人信息，记录里再存一份明文就等于另开一个泄露点；规则测试（`detect_preview`）才回显命中的片段，因为那是规则作者自己输入的样本。启动时把旧版本存下的原文清空。
- 启动播种时内置规则缺失则插入；已存在的内置规则只刷新 pattern（内置规则的 pattern 不可编辑，刷新不丢用户设置），名称、严重度、启用状态保持用户所设。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `rule_service.py` | 核心 | 风险规则 CRUD 服务；播种内置规则并刷新已存内置规则的 pattern；停用旧 `allow` 规则；清空旧命中记录里的原文 | — |
| `detection.py` | 核心 | 实时风险检测引擎：`compile_pattern`、带时间预算的 `detect` / `detect_preview`，命中摘要的写法 | — |
| `match_checks.py` | 辅助 | 内置规则 pattern 命中后的确认（身份证校验位、示例值排除、赋值的 value 是否为密钥） | harness `pii_patterns` / `secret_value` |
| `constants.py` | 辅助 | 风险等级、动作、分类常量与默认启用的分类 | — |
| `patterns.py` | 辅助 | 构造规则 pattern 的工具（隐私检测器源、关键词整词匹配）与共用片段（赋值、厂商前缀密钥） | — |
| `builtin_rules.py` | 辅助 | 个人信息与安全凭证内置规则的定义，汇总出全部 31 条 | harness `pii_patterns` / `card_context` |
| `builtin_business_rules.py` | 辅助 | 公司、客户、财务法务、政治军事内置规则的定义 | — |
