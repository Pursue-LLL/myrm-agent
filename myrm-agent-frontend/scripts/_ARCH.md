# scripts/ 模块架构

## 架构概述

开发/CI 脚本（非运行时）。Python 门禁与 Bun/Node 工具并存；CI 产物在 `scripts/ci/`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `check_fractal_docs.py` | 分形 `_ARCH.md` 门禁（strict roots + recursive baseline）；禁止 `tsconfig.json` include 写入 `.next-isolated-*` |
| `check_file_line_budget.py` | TS/TSX 400 行预算门禁 |
| `check_typescript_strict.py` | `tsc --noEmit` strict 错误数门禁（`ci/typescript_strict_baseline.txt`；`tsconfig.json` `strict: true`） |
| `check_barrel_exports.py` | 跨域 `index.ts` 桶导出白名单门禁 |
| CI lockfile policy | `frontend-build.yml` 断言无 `package-lock.json`（bun.lock 为 SSOT） |
| `ci/fractal_docs_baseline.txt` | 递归扫描豁免目录（当前无条目） |
| `ci/file_line_budget_baseline.txt` | 存量超大文件豁免列表 |
| `ci/barrel_whitelist.txt` | 跨域 barrel 白名单（feature 内 barrel 由路径规则允许） |
| `verify-i18n.mjs` | 六语系 i18n 全量门禁：key parity（缺键=ERROR / 孤儿键=ERROR）、叶子类型一致、ICU 占位符变量一致、翻译壳检测（`collectTranslationShells` + 豁免见 `i18n-shell-allowlist.json`）、glossary forbidden（de/ko/ja/zh-TW，`i18n-glossary.json`，支持 `/正则/` 包裹的 Regex 模式，如 `/クエリ完(?!了)/` 拦截「X完」后缀残留而不误伤「X完了」，正则加载时预编译复用并 fail-fast 校验非法表达式）、双语对照脏值检测（非拉丁文字区间 `NON_LATIN_RE` 覆盖汉字+假名+谚文，拦截 "はい / Yes" 类脏值）、异常哨兵；另含 en 纯净门禁（SSOT 不得混入非拉丁）+ ko/de 非本语言文字纯净门禁（拉丁/谚文系语言文案出现汉字或日文假名即残留，de 额外拦截谚文，语言名与 합니다体/합니다체 术语豁免）+ zh-TW/ja 简体独有字形纯净门禁（繁体/日文文案出现简体独有字形即残留，zh-TW 字形集合读 `zh-simplified-glyphs.txt`、ja 读 `ja-simplified-glyphs.txt`，两门禁共用豁免键，词级残留走 glossary forbidden，语言名与 합니다体 术语豁免）+ zh/ja/ko/zh-TW 句子级纯英文残留门禁（非拉丁系语言整条文案仍是英文句子即残留，值≠en 且纯 ASCII 且含 ≥2 纯字母英文单词且带句尾标点或英文功能词；字段名/品牌名/单技术词如 Token/App ID/Bot Token/Alibaba Cloud 天然豁免，与 9g/9h/9j「混入字形」检测互补拦截「整条还是英文」，de 拉丁语系不适用由 9g + glossary 兜底）；纯净性检测对数组叶子逐元素生效；另有 SSR shell/deferred namespace 门禁 + 关键 namespace keys（`pretest` + CI） |
| `verify-i18n-references.mjs` | 代码引用 → en.json（SSOT）键存在性门禁（9l）：静态扫描 `src/**\/*.{ts,tsx}`，提取 `useTranslations('ns')`/`useTranslations()`/`getTranslations({namespace})` 绑定的 `t('key')` 调用，按「最近前驱同名绑定」归因命名空间后逐一 resolve 到 en.json；调用位于同名绑定声明之前（helper 前置定义、t 由组件体传入，如 PushNotificationCard 的 `stateLabel`）时退化为「同名绑定命名空间并集」验证（任一候选存在即通过，props 传 t 且无文件内绑定自动跳过，防漏检 pushStatus 类真实缺失）；`showI18nToast` 的 `titleKey`/options 中 `descriptionKey`/`action.label` 为完整键引用，独立于命名空间归因直接校验（正则锚定在 `showI18nToast(` 之后避免误抓普通对象属性；三元 descriptionKey/action.label `cond ? 'a' : 'b'` 由专用正则提取两个分支键，比较操作数如 `=== 'no_boards'` 位于 `?` 前不误报）；所有 `t()` 调用一律纳入检查——`{ fallback: 'x' }` 只是 next-intl 插值对象而非兜底（use-intl 的 translateFn 只有第 4 位置参数才是 fallback，且 TS 类型签名禁止该用法），不得因假 fallback 跳过（否则漏检 Agent.fleet.builtin 类真实缺失）；动态/模板 key、测试文件与构建产物跳过；补 verify-i18n.mjs 的测量盲区——后者只校验 locale 间 parity/纯净性，无法发现「组件引用但 SSOT 不存在」的键（运行时无 getMessageFallback 直接显示原始 key = MISSING_MESSAGE）；接入 `verify:i18n`（`pretest` + CI 继承） |
| `generate-simplified-glyphs.mjs` | 从 `locales/zh.json` 简体语料生成两类简体独有字形集合（opencc-js 单字转换）：zh-TW（cn→tw，豁免台湾合法两体字 台/准/于/伙/占/里/游/干）输出 `zh-simplified-glyphs.txt`（`verify-i18n.mjs` 9h 门禁读取）、ja（cn→jp，豁免日文合法同形/新字体字 体/与/云/个/台/准/于/占/里/游/干/伙/携/进/万/发/当/回）输出 `ja-simplified-glyphs.txt`（9j 门禁读取）；兜底字形集合均经目标转换器校验（非本目标语言简体独有字形不收录，防日文合法字误伤）；`--check` 模式供 pretest 强制校验两集合同步（zh.json 更新未重生成即 CI 失败）；zh 文案新增简体字后应重跑：`bun scripts/generate-simplified-glyphs.mjs` |
| `zh-simplified-glyphs.txt` | zh-TW 简体独有字形集合（单行字符集，opencc cn→tw 从 zh 语料生成；勿手改，重生成见 `generate-simplified-glyphs.mjs`） |
| `ja-simplified-glyphs.txt` | ja 简体独有字形集合（单行字符集，opencc cn→jp 从 zh 语料生成，仅收录相对日文新字体确实简化的字形；勿手改，重生成见 `generate-simplified-glyphs.mjs`） |
| `verify-stable-mocks.mjs` | next-intl mock 稳定性门禁：扫描全部测试文件，硬拦截不稳定 mock（`useTranslations: () => (key) => ...` 箭头简写 / `() => { return (key) => ... }` 块体返回），防 Vitest OOM 复发（`lint` + `pretest` 前置） |
| `i18n-shell-core.mjs` | 翻译壳检测共享逻辑（`isLegitSameValue` 值整体类型判据：含非 ASCII/URL/纯路径/邮箱/域名 → 合法保留；无空格 token：全大写国际缩写（`MCP`/`FAQ`/`URL`）→ 合法，含非字母结构（`-`/`/`/`@`/`#`/数字等，如 `sk-...`、`spaces/xxxxx`、`@bot:matrix.org`）→ 合法，纯英文单词（`Active`/`Paused`）或纯单词+省略号（`Loading...`）→ 判壳；去除 ICU 占位符后不再含英文实义词（≥2 字母）→ 纯格式模板（如 `{count} / {max}`）→ 合法；其余含英文实义词的值 → 判为翻译壳（需翻译或由 allowlist 显式豁免）。仅豁免具体格式，不含 `{}$%^`、`/`、`...` 字符级一刀切豁免，避免「Loading...」「Task {taskId} resumed」等未翻译英文漏检；`collectTranslationShells`/`isTranslationShell` 等；verify-i18n 与 dump-remaining 共用，防 gate 口径漂移） |
| `i18n-patch-apply.mjs` | 将 `translation-patches/<locale>/*.json` 深度合并进 `locales/<locale>.json`（内容补齐工作流） |
| `i18n-build-patch.mjs` | 扁平 key→翻译 JSON 构建嵌套 `translation-patches` 补丁树 |
| `i18n-de-bulk-translate.py` | 从 en SSOT 批量机翻 de 剩余壳（Google Translate + placeholder 保护；缓存 `translation-patches/de/auto-translated-overrides.json`） |
| `i18n-de-apply-cache.py` | 将 `auto-translated-overrides.json` 回写到 `locales/de.json`（壳清零前的增量应用） |
| `i18n-de-fix-remaining.mjs` | de 收尾：认知词/渠道 Connect 文案壳 + glossary forbidden 键修正 |
| `i18n-dump-remaining.mjs` | 按 `i18n-shell-core.mjs` 同款壳检测逻辑导出某语言剩余翻译壳清单（TSV/JSON，支持 `--limit`/`--offset`/`--stats`） |
| `i18n-glossary.json` | Native QA 术语表 SSOT（de Sie-Form + ko 敬语约束 + ja です・ます体约束与禁止模式 + zh-TW 繁體约束；`forbidden` 由 `verify-i18n.mjs` 强制执行（支持 `/正则/` 模式），ja 用于拦截中文乱码残留（词汇级中文独有词，含纯同形词——每个字形合法但组合为日语不存在的词，如 文件/窗口/屏幕/信息/提交/刷新/小伙伴/演示文稿/跟随/摸回数/搞定 + 中文介词残留如 按名前/按ユーザー/以アクセス/移動端/検査器/必須はい/に対する象 + 语序乱码 + 中文式组合残留如 終ログイン/首ページ/使用 Google ログイン/終サンドボックス/最ビジーツール/首字/にあなた啦/見る見る + 宾语+动词+失敗 中文动宾句残留如 リセットコンテナ環境/承認下書き/キャンセルピン留め/テンプレート適用失敗 + 简体独有词 + 动词+空格+名词 动宾按钮残留如 選択 MCP/作成 APIキー/エクスポート CSV/クリア OAuth/承認 + 中文式短标签拟声/语气词残留如 好！/完！/嘭！/啦！ + 中文「X完」后缀残留（正则 `/X完(?!了)/` 拦截，如 クエリ完/コンパイル完/スキャン完/準備完）+ 動詞+名詞 动宾按钮语序残留（如 確認削除/開く設定/閉じるパネル/追加ルール/選択ゴール/入力スキル名前，名词复合词如 検索サービス/実行モード 不受影响）+ Shadow）、zh-TW 用于拦截豁免字形字的简体词残留与两岸差异词（标准/云端/用于/基于/里面/关于/屏幕/信息/窗口/兼容/搜索/界面/支持/保存/刷新/文件夾/拖拽/退出登入/全屏/插件 等 41 词）；de/ko rules 声明汉字纯净约束、zh-TW rules 声明简体字形纯净约束） |
| `i18n-shell-allowlist.json` | 翻译壳检测豁免清单：真正不可翻译的值（品牌/凭据字段名/占位示例/纯格式模板如 `PID {pid}`、`{wu} WU`、`TLS / mTLS`、`sk-...`）与键路径 |
| `translation-patches/` | 各语言内容补齐补丁目录（`<locale>/batch-NN.json` 等嵌套 JSON 补丁，供 `i18n-patch-apply.mjs` 深度合并；应用前以 `i18n-dump-remaining.mjs` 导出剩余壳清单） |
| `verify-sw-push.mjs` | `public/sw.js` 须含 Web Push handler、URL 消毒、`resolvePushClientFocusAction`、`.navigate(`（`build:sw-inject` + Serwist inject-manifest + CI） |
| `build-sw-src.mjs` | esbuild 打包 `src/app/sw.ts` → `.serwist/sw-inject-src.js`（inject-manifest 入口，解析 lib import） |
| `scan-home-i18n-shell.mjs` | home-route `settings.*` 引用须在 SSR shell（CI via verify-i18n） |
| `verify-shell-i18n-runtime.mjs` | 运行时 SSR HTML / deferred API 校验（dev；shell 清单从 locale-manifest 解析） |
| `split-locale-namespaces.mjs` | 从 `locales/{lang}.json` 生成 `locales/namespaces/`（`dev.ts` / `build` / `build:tauri` / `prestart` / `pretest` 前置） |
| `sync_i18n.py` | 从 en（SSOT）补全其余 5 种语言缺失键（本地维护） |
| `dev.ts` | locale split + Next dev 入口（`dev` / `dev:lan` / `dev:clean`；`dev-server.lock` 健康跳过） |
| `dev-lock.ts` | dev lock 读写与 LISTEN 健康判定 |
| `port-cleanup.ts` | `:3000` LISTEN-only 清理 |
| `cleanup.ts` | 本地 dev 残留清理（`:3000` 进程、stale lock、非 active 的 `.next-isolated-*`、dev log truncate、stray `package-lock.json`、`strip_isolated_tsconfig.py`） |
| `strip_isolated_tsconfig.py` | 移除 Next isolated build 写入的 `tsconfig.json` include 与 `next-env.d.ts` 污染；重置 next-env 为 `.next/dev/types/routes.d.ts` + `root-params.d.ts`；E2E `release_runtime` teardown 与 `cleanup.ts` 调用 |
| `generate-artifact-types.ts` | 工件类型生成 |
| `export-known-sse-event-types.ts` | SSE 事件类型导出对齐 |
| `__tests__/` | 脚本相关单测 |

## 依赖

- 仓库根 `package.json` scripts 引用本目录
- `check_*` 由 CI `frontend-build.yml` 调用

## 约束

- 新 CI 门禁脚本放本目录并在本 `_ARCH.md` 与根 `_ARCH.md` CI 节登记
- baseline 文件仅通过 `--write-baseline` 更新，禁止手改豁免逻辑
- `ci/barrel_whitelist.txt` 跨域 barrel 条目须与根 `_ARCH.md` 桶表同步，手改后跑 `check_barrel_exports.py` 验证
