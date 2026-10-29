# code_graph 模块架构

## 职责定位
本地、零外部服务依赖的代码结构索引：把工作区内的 Python 与 TypeScript/JavaScript 源文件解析为符号、调用点、继承和导入关系，存入 SQLite，供 Agent 工具 `code_graph_tool` 按结构提问（符号定义、调用方、被调用、子类、导入方、直接调用它的测试）。

两条贯穿全模块的事实：

- 调用点的被调用者只记录调用处的原文（`Name` 或点分属性链），不解析到具体定义。因此 `callers` 按「整串相等」或「最后一段同名」匹配，每行用 `match`（`exact` / `name`）标明，并由 `count_definitions` 给出同名定义数；同名定义数大于 1 时，`match=name` 的行只是候选。
- 索引按文件指纹增量同步：`index_directory` 可以反复运行，目录没变时只有一次文件列举和每个文件一次 `stat`；首次索引每解析 `INDEX_BATCH_FILES` 个文件落库一次，内存里只留一批解析结果，同一索引库的同步在进程内串行。

## 核心文件清单
- `models.py`: 数据模型（`SymbolNode`、`CallEdge`、`InheritanceEdge`、`ImportEdge`、一个文件的解析结果 `ParsedFile`、同步统计 `IndexStats`）。
- `ast_extractor.py`: 符号与调用抽取器。Python 用原生 `ast`，一次迭代遍历：`if`、`try`、`with` 内的定义与导入同样被找到；每个调用只记给最内层的函数，模块层与类体里的调用记给模块名，装饰器、默认值、基类表达式在定义时执行，所以记给外层；只有直接位于类体内的函数是 `method`，嵌套函数是 `function`；不是合法 Python 的源码让 `extract()` 返回 `False`。JS/TS 用按行正则（不记录导入，`importers` 只覆盖 Python）：只识别行首无缩进的 `class`、`function` / `async function` 与 `const f = (...) =>` 声明，各产出一个符号（函数的 `line_end` 与类同口径，等于声明行），类方法、嵌套函数、`export default function` 与带泛型的函数不产出符号；调用按行扫描，每个调用只记一条边，归属最近一个在其之前声明的函数（不跟踪作用域结束），第一个函数声明之前的调用归模块。`module_name_for` 是两个抽取器共用的模块名规则（由相对索引根的路径得到点分名），同名文件位于不同目录时限定名不会冲突。
- `graph_store.py`: SQLite（WAL）存储。`files` 表保存每个文件的指纹，符号、调用、继承、导入四张表按文件归属；`apply_changes` 在一个事务内先删除已消失与已改动文件的全部行，再写入新的解析结果（符号只存位置与文档注释，不保存源码文本；`reset` 在写事务内判断，只在尚无任何文件记录时清空整库以接管没有来源记录的旧库，已有文件记录时不清，所以一次运行不会清掉别的运行已落库的批次）；新库切换到 WAL 时遇到并发会重试（`_enable_wal`），多个 Agent 同时打开同一工作区不会失败；所有 `LIKE` 查询都转义 `_` 与 `%`，名字按字面匹配。`get_tests_calling` 只返回按路径约定（位于 `tests/`、`test/`、`__tests__/` 目录，或文件名为 `test_*.py`、`*_test.py`、`*.test.ts`、`*.spec.ts` 等）判定为测试文件内的直接调用点。
- `service.py`: `CodeGraphService` 门面。`index_directory` 的文件清单来自 harness 的 `WorkspacePathIndexer`（git 仓库走受限 `git ls-files`，否则遍历目录，遵循忽略规则），只收 `SOURCE_SUFFIXES`，排除 `EXCLUDE_DIRS`、符号链接与特殊文件、超过 `MAX_SOURCE_BYTES` 的文件；用 `(mtime_ns, size)` 判定新增、改动与删除，无法读取、或不是合法 Python 的文件计入 `skipped_files`，且不记指纹，每次运行都会重试；文件清单触及枚举上限时 `IndexStats.truncated` 为真（超出的文件不被索引）；读取时去掉 UTF-8 BOM；解析结果每累积 `INDEX_BATCH_FILES`（500）个文件调用一次 `apply_changes`，只有第一批清掉没有来源记录的旧条目，已删除的文件最后统一处理，中途失败后已落库的文件带着指纹，下一次运行只解析其余文件；同一索引库（按库路径）的 `index_directory` 在进程内持锁串行，被取消的工具调用留下的线程还在运行时，下一次调用等它结束并复用已落库的文件。随后提供 `resolve`、`definition`、`callers`、`callees`、`implementors`、`importers`、`tests_calling` 七种查询和 `definition_count`。
- `agent_tool.py`: Agent 工具 `code_graph_tool`。动作与 `service.py` 的七种查询一一对应；每次调用先同步索引再查询，结果最多 50 行，附 `total`、`definitions` 与 `notes`（文件清单被截断、超出上限、同名定义、JS/TS 近似、未索引文件、无结果时的建议）；清单被截断时 `notes` 明说部分文件未索引、查不到不代表没有，改用 grep。索引库位于持久卷的 `code_graph/` 下、按工作区路径哈希命名，不写入工作区。`append_code_graph_tool` 仅在用户启用了预置技能 `repo-call-graph` 且 Agent 有工作区时挂载；工具描述与参数 schema 是常量，不含工作区路径或统计，不影响提示词缓存。

## 已知限制
- JS/TS 的归属是近似的（见 `ast_extractor.py`），结果里会带提示。
- 大小与修改时间都没变的改写不会被发现。
- 同一目录下同名的 `.ts` 与 `.js`（例如提交了编译产物）限定名相同，后写入的覆盖先写入的符号。
- 索引库约为源码体积的 4 倍（harness 仓库 45.1 MB 源码对应 185.7 MB），按工作区路径存放，不随工作区删除而清理。
- 不是合法 Python 的文件（例如 Python 2）得不到任何符号。
- 文件清单受 `WorkspacePathIndexer` 的文件数上限约束，超出部分不被索引；触及上限时工具结果的 `notes` 会提示，此时「没有调用方」只是未确认。
- 首次索引大型仓库需要数秒到数十秒，之后只处理变化的文件。
- 串行只在进程内；两个进程同时首次索引同一个库时各自解析一遍，结果一致，只是重复耗时。

## 架构边界
属于 Server 业务层提供的预置代码智能能力，不侵入 Harness 核心执行框架；对 Harness 只使用公开的 `WorkspacePathIndexer` 与持久卷根路径。Agent 侧的挂载点在 `app/ai_agents/general_agent/factory.py`，工具层级登记在 `tools/_tool_layer_bootstrap.py`（EXTERNAL）。
