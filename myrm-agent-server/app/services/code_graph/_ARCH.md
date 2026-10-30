# code_graph 模块架构

## 职责定位
本地、零外部服务依赖的代码结构索引：把工作区内的 Python 与 TypeScript/JavaScript 源文件解析为符号、调用点、继承和导入关系，存入 SQLite，供 Agent 工具 `code_graph_tool` 按结构提问（符号定义、调用方、被调用、子类、导入方、直接调用它的测试）。

三条贯穿全模块的事实：

- 调用点的被调用者只记录调用处的原文（`Name` 或点分属性链），不解析到具体定义。因此 `callers` 按「整串相等」或「最后一段同名」匹配，每行用 `match`（`exact` / `name`）标明，并由 `count_definitions` 给出同名定义数；同名定义数大于 1 时，`match=name` 的行只是候选。
- 索引按文件指纹增量同步：`index_directory` 可以反复运行，目录没变时只有一次文件列举和每个文件一次 `stat`；每解析 `INDEX_BATCH_FILES` 个文件或累计 `INDEX_BATCH_BYTES` 字节源码就落库一次（首次索引与大批改动一样；解析结果的大小随源码体积增长，所以不只按个数切），内存里只留一批解析结果，同一索引库的同步在进程内串行。
- 抽取结果就是索引内容：文件指纹没变就不会重新解析，所以任何改变表结构或抽取结果的修改都必须递增 `models.INDEX_FORMAT_VERSION`。索引库文件名带这个版本（`<工作区路径哈希>.v<版本>.db`），换版本就是换一个新库从头索引，`agent_tool.py` 在打开库之前删除同一工作区其他版本的库文件（含 WAL 文件）。`tests/services/code_graph/test_code_graph_extraction_golden.py` 把一组样本的抽取结果指纹与版本号绑在一起：抽取结果变了而版本没递增，测试失败。

## 核心文件清单
- `models.py`: 数据模型（`SymbolNode`、`CallEdge`、`InheritanceEdge`、`ImportEdge`、一个文件的解析结果 `ParsedFile`、同步统计 `IndexStats`）。
- `ast_extractor.py`: Python 符号与调用抽取器，用原生 `ast`，一次迭代遍历：`if`、`try`、`with` 内的定义与导入同样被找到；每个调用只记给最内层的函数，模块层与类体里的调用记给模块名，装饰器、默认值、基类表达式在定义时执行，所以记给外层；只有直接位于类体内的函数是 `method`，嵌套函数是 `function`；不是合法 Python 的源码让 `extract()` 返回 `False`。`module_name_for` 是 Python 与 JS/TS 两个抽取器共用的模块名规则（由相对索引根的路径得到点分名），同名文件位于不同目录时限定名不会冲突。
- `js_ts_extractor.py`: TypeScript/JavaScript 抽取器，用 tree-sitter 语法树（`.ts` 用 typescript 语法，`.tsx`、`.jsx`、`.js` 用 tsx 语法），接口与 Python 抽取器一致。符号：函数声明（含生成器、`export default function Name`）、绑定到 `const` / `let` / `var` 的箭头函数与函数表达式、类（声明、抽象类、绑定到变量的类表达式）、类的方法、构造函数、访问器与值为箭头函数的类属性（均为 `method`）、嵌套的具名函数；对象字面量的成员与匿名函数不是符号；`line_end` 是声明节点的结束行。调用：标识符或成员链形式的 `call_expression` 与 `new_expression`，被调用者文本沿用 Python 的点分链规则，调用位置记在被调用的名字上；调用归属最内层的非类作用域，类体、装饰器与参数默认值里的调用记给外层，模块层记给模块名；`extends` 记基类原文（`React.Component`），`implements` 不记。用游标迭代遍历语法树一次，每个节点的开销与嵌套深度无关；不用 QueryCursor，因为它每个节点的开销随树深增长（15 万层括号要 35 s，且全程持有 GIL），同时打开超过 32,767 个匹配时会静默丢匹配（4 万个链式调用只留下 32,767 个）；语法有错的文件按能解析出的部分抽取，`extract()` 总是返回 `True`。不抽取导入，`importers` 只覆盖 Python。
- `graph_store.py`: SQLite（WAL）存储。`files` 表保存每个文件的指纹，符号、调用、继承、导入四张表按文件归属；`apply_changes` 在一个事务内先删除已消失与已改动文件的全部行，再写入新的解析结果（符号只存位置与文档注释，不保存源码文本；`reset` 在写事务内判断，只在尚无任何文件记录时清空整库以接管没有来源记录的旧库，已有文件记录时不清，所以一次运行不会清掉别的运行已落库的批次）；新库切换到 WAL 时遇到并发会重试（`_enable_wal`），多个 Agent 同时打开同一工作区不会失败；所有 `LIKE` 查询都转义 `_` 与 `%`，名字按字面匹配；`resolve` 的 `路径:行号` 目标返回包含该行的符号，范围小的在前，范围相同时模块排在最后。`get_tests_calling` 只返回按路径约定（位于 `tests/`、`test/`、`__tests__/` 目录，或文件名为 `test_*.py`、`*_test.py`、`*.test.ts`、`*.spec.ts` 等）判定为测试文件内的直接调用点。
- `service.py`: `CodeGraphService` 门面。`index_directory` 的文件清单来自 harness 的 `WorkspacePathIndexer`（git 仓库走受限 `git ls-files`，否则遍历目录，遵循忽略规则），只收 `SOURCE_SUFFIXES`，排除 `EXCLUDE_DIRS`、符号链接与特殊文件、超过 `MAX_SOURCE_BYTES` 的文件；`.py` 交给 Python 抽取器，其余后缀交给 JS/TS 抽取器；用 `(mtime_ns, size)` 判定新增、改动与删除，无法读取、或不是合法 Python 的文件计入 `skipped_files`，且不记指纹，每次运行都会重试；文件清单触及枚举上限时 `IndexStats.truncated` 为真（超出的文件不被索引）；读取时去掉 UTF-8 BOM；解析结果每累积 `INDEX_BATCH_FILES`（500）个文件或 `INDEX_BATCH_BYTES`（8,000,000）字节源码调用一次 `apply_changes`，只有第一批清掉没有来源记录的旧条目，已删除的文件最后统一处理，中途失败后已落库的文件带着指纹，下一次运行只解析其余文件；同一索引库（按库路径）的 `index_directory` 在进程内持锁串行，被取消的工具调用留下的线程还在运行时，下一次调用等它结束并复用已落库的文件。随后提供 `resolve`、`definition`、`callers`、`callees`、`implementors`、`importers`、`tests_calling` 七种查询和 `definition_count`。
- `agent_tool.py`: Agent 工具 `code_graph_tool`。动作与 `service.py` 的七种查询一一对应；每次调用先同步索引再查询，结果最多 50 行，附 `total`（匹配总数，不是显示的行数）、`definitions` 与 `notes`（文件清单被截断、超出上限、同名定义、未索引文件、无结果时的建议）；清单被截断时 `notes` 明说部分文件未索引、查不到不代表没有，改用 grep。索引库位于持久卷的 `code_graph/` 下，文件名是工作区路径哈希加 `INDEX_FORMAT_VERSION`，不写入工作区。`append_code_graph_tool` 仅在用户启用了预置技能 `repo-call-graph` 且 Agent 有工作区时挂载；工具描述与参数 schema 是常量，不含工作区路径或统计，不影响提示词缓存。

## 已知限制
- JS/TS 只记录标识符与成员链形式的调用：括号、下标形式的被调用者、`super()`、`import()` 与标签模板不记录；只有签名没有函数体的声明（`.d.ts`、函数重载签名）不产出符号；`.mjs`、`.cjs` 不在 `SOURCE_SUFFIXES` 内。
- tree-sitter-typescript 有解析不了的写法，例如类型参数里的 `typeof import('x')`（vitest 的 `importOriginal<typeof import('x')>()` 就是这种）：遇到时只丢这一处的调用，文件其余部分照常抽取。本仓库前端 `src` 的 4,818 个源文件、238,301 个调用点与 TypeScript 编译器逐一比对：符号全部一致，调用点召回 99.93%（漏 172 个，其中 149 个在有语法错误的文件里），精确率 100.00%（多记 1 个），已匹配的调用点上被调用者文本与归属全部一致；4,818 个文件中 134 个有语法错误。
- 具名定义最多嵌套 `MAX_SCOPE_DEPTH`（32）层，更深的定义不是符号，其中的调用记给最深的一个：限定名重复每一层外层的名字，1 MB 文件嵌套 7.6 万层曾占用 5 至 6.5 GB 内存。
- JS/TS 解析没有超时：`MAX_SOURCE_BYTES` 限定单文件 1 MB。20 种 1 MB 以内的对抗性形状（深层括号、数组、泛型、三元、JSX、未闭合括号、链式调用、参数里的调用、嵌套定义等）实测每个文件 0.02 至 6.6 s（机器负载约 50；有一次读数 10.9 s，重测为 2.2 s）。最慢的是未闭合泛型 `f<a<a<…`，耗时在 tree-sitter 解析本身而不在遍历，这里无法约束。py-tree-sitter 0.25 的 `progress_callback` 返回 `False` 时会让进程崩溃，不能用来中断解析。
- `tree-sitter` 固定在 `>=0.25.2,<0.26`：0.26.0 读取 `Point.row` / `.column` 时过度释放引用，解析较大文件时随机崩溃整个进程（py-tree-sitter#505），修复尚未发布；放开版本前必须确认这一点。
- 大小与修改时间都没变的改写不会被发现。
- 同一目录下同名的 `.ts` 与 `.js`（例如提交了编译产物）限定名相同，后写入的覆盖先写入的符号。
- 索引库约为源码体积的 4 倍（harness 仓库 45.1 MB 源码对应 185.7 MB），按工作区路径存放，不随工作区删除而清理。
- 不是合法 Python 的文件（例如 Python 2）得不到任何符号。
- 文件清单受 `WorkspacePathIndexer` 的文件数上限约束，超出部分不被索引；触及上限时工具结果的 `notes` 会提示，此时「没有调用方」只是未确认。
- 首次索引大型仓库需要数秒到数十秒，之后只处理变化的文件；首次调用受 Agent 工具默认 60 s 超时与最多 2 次尝试约束，超时后索引线程在后台继续，下一次尝试等它结束并复用成果；两次都超时则本次调用报错，之后每次调用（各有 2 次尝试）最多再等约 121 s，索引在后台跑完后即可直接使用。
- 串行只在进程内；两个进程同时首次索引同一个库时各自解析一遍，最终结果一致，只是重复耗时。
- 超过一批（500 个文件或 8 MB 源码）的同步不是单个原子事务：同步进行中，不持有同步锁的读者可能看到新旧混合的图；`code_graph_tool` 在查询前先等待同步完成，不受影响。
- 结果最多 50 行：`callers`、`tests_calling` 按文件路径、`implementors` 按类名排序后取前 50 行，被截掉的部分不可见；这三个动作按最后一段名字匹配，限定名返回同样的行，只能在关心的目录里用 grep 缩小；`resolve` 与 `importers` 用限定名可以缩小，`callees` 按行号取前 50 行。每个动作超过上限时给出的建议由 `agent_tool.py` 的 `_Action.cut_hint` 自述，新增动作必须填写；预置技能 `assets/prebuilt_skills/repo-call-graph/SKILL.md` 只指向 `notes`，不复制各动作的建议。

## 架构边界
属于 Server 业务层提供的预置代码智能能力，不侵入 Harness 核心执行框架；对 Harness 只使用公开的 `WorkspacePathIndexer` 与持久卷根路径；JS/TS 解析依赖第三方原生扩展 `tree-sitter` 与 `tree-sitter-typescript`。Agent 侧的挂载点在 `app/ai_agents/general_agent/factory.py`，工具层级登记在 `tools/_tool_layer_bootstrap.py`（EXTERNAL）。
