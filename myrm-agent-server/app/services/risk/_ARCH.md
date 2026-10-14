# services/risk 模块架构

## 架构概述

风险管控服务层。提供风险规则管理和实时风险检测能力。

- 检测在事件循环上同步运行，输入是任何聊天发送者可控的文本，所以匹配用 `regex` 包，每条规则对一段文本有 `MATCH_TIMEOUT_SECONDS` 的时间预算；超时的规则按命中处理（宁可拦下，也不放行一条专为拖垮规则构造的消息）。
- 规则的 pattern 先过 harness 的 `pattern_problem`（计数重复展开过大会在编译时吃光内存），再编译；校验、启动加载、规则测试共用 `compile_pattern`，`regex` 默认模式对普通 `re` 写法的含义相同，只在 `[[:alpha:]]` 这类边角写法上不同。
- 内置的邮箱、手机号、身份证、银行卡规则直接取隐私检测器（harness `pii_patterns` / `card_context`）的 pattern 源，并在命中后做分类器同样的确认（身份证校验位、示例值排除），渠道闸门与隐私分类器对「什么算个人信息」只有一份定义。
- 启动播种时内置规则缺失则插入；已存在的内置规则只刷新 pattern（内置规则的 pattern 不可编辑，刷新不丢用户设置），名称、严重度、动作、启用状态保持用户所设。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `rule_service.py` | 核心 | 风险规则 CRUD 服务；播种内置规则并刷新已存内置规则的 pattern | — |
| `detection.py` | 核心 | 实时风险检测引擎：`compile_pattern`、带时间预算的 `detect` / `detect_preview` | — |
| `match_checks.py` | 辅助 | 内置规则 pattern 命中后的确认（身份证校验位、示例值排除） | harness `pii_patterns` |
| `constants.py` | 辅助 | 风险等级和阈值常量、内置规则定义（个人信息规则取隐私检测器的 pattern 源） | harness `pii_patterns` / `card_context` |
