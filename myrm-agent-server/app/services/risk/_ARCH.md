# services/risk 模块架构

## 架构概述

风险管控服务层。提供风险规则管理和实时风险检测能力。

- 检测的输入是任何聊天发送者可控的文本，所以匹配用 `regex` 包，每条规则对一段文本有时间预算 `match_budget(len(text))`：不短于 `MATCH_TIMEOUT_SECONDS`，长文本再按每百万字符 `MATCH_SECONDS_PER_MEGACHAR` 放宽（最慢的内置规则在日志文本上约 0.13 s / 百万字符，预算取 0.5 s，约 4 倍余量；固定预算会把 5 MB 的无害日志粘贴误判成命中）；超时的规则按命中处理（宁可拦下，也不放行一条专为拖垮规则构造的消息）。
- 短文本（≤ `_INLINE_DETECT_CHARS` = 32,000 字符，实测 < 7 ms）在事件循环上直接匹配；更长的经 `detect_async` 放到工作线程，`regex` 匹配 `str` 时释放 GIL，事件循环不被占住（1 MB 同步匹配会卡住循环约 195 ms，线程化后 5 MB 的卡顿只有几毫秒）。出站渠道闸门 `apply_outbound_risk_gate` 仍是同步 `detect`，同样受益于按长度放宽的预算。
- 规则的 pattern 先过 harness 的 `pattern_problem`（计数重复展开过大会在编译时吃光内存），再编译；校验、启动加载、规则测试共用 `compile_pattern`，`regex` 默认模式对普通 `re` 写法的含义相同，只在 `[[:alpha:]]` 这类边角写法上不同。
- 规则只有一种效果，所以没有动作字段：命中即拦下，不想让一条规则生效就停用它。第一条命中的规则即拦下这段文本。
- 默认启用的只有「安全凭证」分类（`DEFAULT_ENABLED_CATEGORIES`，8 条）：凭证从不需要出现在一条消息里；个人信息、公司、客户、财务法务、政治军事这 23 条是个人助理的日常话题（姓名、邮箱、合同、预算），由用户按自己的数据打开。播种只对新插入的规则套用这一默认，已存在的规则保持用户所设。
- 内置的邮箱、手机号、身份证、银行卡规则直接取隐私检测器（harness `pii_patterns` / `card_context`）的 pattern 源，并在命中后做分类器同样的确认（身份证校验位、示例值排除），渠道闸门与隐私分类器对「什么算个人信息」只有一份定义。
- 下列用户亲手输入、将被智能体读取或执行的文本经 `ingress.screen_user_text` 过闸（入口登记表见 `tests/architecture/test_text_entry_risk_gate.py`）：聊天消息、转向 / 重定向指令、目标文案、IM 的忙时转向与委派、IM 系统命令的参数（`/background`、`/goal`、`/kanban comment` 等直接据文本行动的命令，在 `_dispatch_resolved` 一处过闸，`/steer` 不另设闸门）、子智能体与后台任务的转向 REST、定时任务与心跳的提示词、看板任务的标题 / 描述 / 验收标准 / 评论 / 手工写入的结果 / 移交的结果与说明 / 驳回理由 / 回收理由（下一个智能体的上下文会带上它们）、智能体档案里模型会读的文字（`system_prompt`、`description`、建议提示词、命令绑定的指令；创建与更新都过闸）、AI 创建智能体与提示词生成的意图（含待改写的现有提示词）、批量目录的提示词、技能派生指令、子目标与目标草稿、IM 事件触发的派发（命中的消息不拉起任何任务；命中记录与通知都由同一条消息的回合路径写与发，派发只检测，一条被拦的消息只留一条记录）。刻意不过闸的：IM 附件的内容（文档提取文本放在 `metadata.document_text_blocks`、图片放在 `metadata.image_data_list`，闸门读的是 `msg.content`；语音 / 视频转写已合并进 `msg.content`，会被筛查）、`shell` 类定时任务的 `command` 与看板 `shell` 验收项（是被执行的命令，不是模型读的文字）、任务的 `blocked_reason`（网页没有输入它的界面，IM 的 `/kanban block` 文字已在入站闸门筛查）、智能体运行自己写出的 `result`（不是用户键入的）、已存在的旧数据（只拦本次写入的文本，未改的字段不重新过闸）。检测、写位置记录（记录失败只记 WARNING，文本照拦）都在这一个入口，各入口只决定怎样告知发送者：聊天 SSE 发 `risk_blocked` 事件，IM 回一句固定通知，REST 入口经 `refusal.reject_if_risky` 返回 HTTP 400，`detail` 为 `{code: "risk_held", message, rules: [{rule_id, display_name, severity}]}`（只含规则身份，不含任何句子与原文），前端统一请求层据 `code` 用用户语言弹出同一条提示。新增接受用户任务指令文本的端点必须登记进 `tests/architecture/test_text_entry_risk_gate.py` 并调用对应闸门；该测试还会扫描全部写端点，请求里带 `prompt` / `instruction` / `intent` / `objective` / `goal` 字段而既未登记、也没写明「文本不是给智能体照做的」豁免理由的，测试失败。闸门在上下文守卫的大文本溢出落盘之前：超长粘贴里的密钥因此不会先被写进磁盘文件再被检测；被拦的 IM 消息在返回前会把收件日志条目标为已处理，原文不会留在待重放的日志里。
- 凭证赋值类规则（`credential_assignment` / `cookie_session_like` / `env_file_secret` / `db_connection_string`，连接串的 `value` 是它的密码）的 pattern 捕获 `key` 与 `value`，命中后由 harness `secret_value_span` 判断 `value` 是不是真的密钥（调用、标识符、模板、TypeScript 的非空断言 `process.env.X!`、掩码、普通单词都不算）；值里带省略号的（`Bearer eyJhbGci...`）是被截短的示例，同样不算；指向密钥库的指针（`env:GEMINI_API_KEY`、`vault:secret/data/db#password`）只写了密钥放在哪里，也不算。判断前先截取值自己的范围：值到下一个查询参数（`&k=`）和第一个非 ASCII 标点（中文行文里跟在值后面的全角括号、逗号）为止，非 ASCII 符号（`€`、`£`）留在值里，因为密码里会有；以 `your` / `change` / `replace` / `example` 这类词开头的值（`YourSecurePassword123!`、`CHANGE-TO-A-UNIQUE-64-CHAR-SECRET-KEY`）是文档让读者填的占位，也不算：词在分隔符或结尾处结束，驼峰写法则在下一个大写字母处结束，词后面接着别的字母的是密码本身（`Yourdog2012!`、`ENTERPRISE2012!`）；词前可以有最多 6 个字母加分隔符的厂商前缀（`sk-YOUR_API_KEY`）。会话 / 访问令牌规则（`cookie_session_like`）在此之上再要求值是长而随机的令牌：至少 16 个字符且不是只由可读单词与数字构成（harness `is_reference_token`），所以 `session-1`、`test-token-123` 这类测试夹具不被拦，32 位十六进制的会话 ID 和不透明的 Bearer 令牌会被拦；它还有一个 `Cookie` / `Set-Cookie` 请求头分支，`value` 取到行尾，只检查名字里带 `sess` / `sid` / `auth` / `token` / `jwt` / `login` / `remember` / `secret` / `passw` 的 cookie（`PHPSESSID`、`connect.sid`、`session`），`theme=dark`、`_ga=GA1.2.…` 这类不是凭证，不论多长。键可以带环境变量前缀（`DB_PASSWORD`、`GROQ_API_KEY`、`aws_secret_access_key`：键从 `_` 或 `-` 之后开始）。所以粘贴的代码 `password = input()`、`token = os.environ[...]` 不会被拦，`password: Zk9#mango42` 会。
- `api_key_like` 只匹配以厂商前缀开头的整段 token，不匹配 URL slug 或词尾：`sk-`（含各家兼容中转站的密钥）是闸门自己的，其余取 harness `leak_detector.DISTINCTIVE_KEY_PATTERNS`（前缀本身就能认出密钥的那部分；`vercel_`、`fal_` 这类会命中标识符的短前缀不在其中），不另存一份清单；`test_builtin_rule_precision.py` 要求表里每一种形状都有样本且被拦下，表里新增形状而没有样本时测试失败。
- 纯关键词规则由 `keyword_pattern` 生成：拉丁词按整词匹配（可带复数），`tin` 不会命中 `meeting`，中文词不依赖分词，处处可匹配。
- 命中记录的 `match_summary` 只写位置（`chars:起-止`）或超时标记，不写命中的原文：这些规则要拦的正是密钥与个人信息，记录里再存一份明文就等于另开一个泄露点；规则测试（`detect_preview`）才回显命中的片段，因为那是规则作者自己输入的样本。迁移清空库里既不是位置也不是超时标记的摘要。
- 启动播种时内置规则缺失则插入；已存在的内置规则只刷新 pattern（内置规则的 pattern 不可编辑，刷新不丢用户设置），名称、严重度、启用状态保持用户所设。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `rule_service.py` | 核心 | 风险规则 CRUD 服务；播种内置规则并刷新已存内置规则的 pattern | — |
| `detection.py` | 核心 | 实时风险检测引擎：`compile_pattern`、随文本长度放宽的时间预算 `match_budget`、带预算的 `detect` / `detect_preview`、长文本放工作线程的 `detect_async`，命中摘要的写法 | — |
| `ingress.py` | 核心 | 用户亲手输入文本的统一过闸入口 `screen_user_text`：检测、写位置记录，返回命中结果（`record=False` 只检测不写记录）；各入口自己决定怎样告知发送者 | `detection.py` / `platform_utils` |
| `refusal.py` | 核心 | REST 入口的拒绝契约：`reject_if_risky(*texts)` 逐段过闸、命中即抛 HTTP 400 `risk_held`；`risk_rules_payload` 是 REST 与聊天 SSE 共用的规则载荷（id、名称、严重度） | `ingress.py` |
| `match_checks.py` | 辅助 | 内置规则 pattern 命中后的确认（身份证校验位、示例值排除、赋值的 value 截到自己的范围后是否为密钥，且不是被省略号截短的示例、文档里的占位或密钥库指针；会话 / 访问令牌要求长而随机，`Cookie` 请求头只看凭证类 cookie） | harness `pii_patterns` / `secret_value` |
| `constants.py` | 辅助 | 风险等级、分类常量与默认启用的分类 | — |
| `patterns.py` | 辅助 | 构造规则 pattern 的工具（隐私检测器源、关键词整词匹配）与共用片段（键的起点、赋值、厂商前缀密钥） | harness `leak_detector.DISTINCTIVE_KEY_PATTERNS` |
| `builtin_rules.py` | 辅助 | 个人信息与安全凭证内置规则的定义，汇总出全部 31 条 | harness `pii_patterns` / `card_context` |
| `builtin_business_rules.py` | 辅助 | 公司、客户、财务法务、政治军事内置规则的定义 | — |
