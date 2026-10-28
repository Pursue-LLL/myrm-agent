# lib/syntax/

代码高亮的共享注册表。`prism-react-renderer` 自带的 Prism 只有 28 种语法，产品里却到处用到它没有的语言：shell 命令步骤用 `bash`、聊天里的 bash 围栏代码块、文档预览里的 diff 围栏代码块、文件按扩展名推断出的 java / ruby / toml 等。四个高亮入口经这一个模块取得 Prism 与语言判定，不再各自碰 `prism-react-renderer` 的语法表；高亮的颜色同样只有一份，由 `theme.ts` 给出。

## 文件清单

| 文件                                 | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                       | I/O/P |
| ------------------------------------ | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `prism.ts`                           | 核心 | 注册 bash（含 sh、shell，另把 zsh 指向同一份）、diff、java、ruby、csharp、toml、lua、r、php、dart；导出 `Prism`、`MAX_HIGHLIGHT_LINE_CHARS`（10,000）与 `resolveLanguage(language, code?)`：语言没有语法、或代码里有一行超过上限时返回 `text`，否则原样返回语言名                                                                                                                                          | ✅    |
| `theme.ts`                           | 核心 | `syntaxThemeFor(resolvedTheme)` 给出当前明暗主题的代码着色（`SyntaxTheme`）：One Light / One Dark 里在产品的代码表面上对比度低于 4.5:1 的颜色换成同色相的更深或更浅一档（浅色 6 种：注释、数字与属性名、红、绿、蓝、url；深色 2 种：注释、红），其余颜色保持原样；四个入口都从这里取主题，不再各自选 `themes.oneLight` / `themes.oneDark`                                                                  | ✅    |
| `__tests__/prism.test.ts`            | 测试 | 每种新语法能识别各自的代码片段、`sh/shell/zsh` 别名、原有语法保留、`resolveLanguage` 的名字与长行判定（恰好等于上限不拦、多一个字符才拦、CRLF 与首行同样生效）；`EXT_TO_LANGUAGE` 里的每个语言都必须能被 `resolveLanguage` 原样解析，增删语法或映射时两边对不上就失败                                                                                                                                      | ✅    |
| `__tests__/theme.test.ts`            | 测试 | 明暗两套主题里每个颜色在每个能出现它的表面上都不低于 4.5:1（面板、聊天代码块、步骤面板、悬停行、diff 增删行底色，以及 diff 围栏块里按语法只会出现的增删与 hunk 行底色）；行号用的次要文字色（`--muted-foreground`，从 `globals.css` 读）在同样的表面上也不低于 4.5:1；主题与原版只有颜色不同，原版里已经达标的颜色保持原样；替换表的键对不上原版（升级后写法变了）时以「某颜色在某表面上不达标」的形式失败 | ✅    |
| `__tests__/grammarSurfaces.test.tsx` | 测试 | 四个真实入口（`CodeBlock`、`EnhancedSyntaxHighlighter`、`DiffViewer`、`LineNumberedCode`）里 bash 的关键字与字符串确实带上本模块调色板里的颜色，行号带次要文字色类，长行文本在四处都保持无色；直接经 `CodeBlock` 渲染的 diff 围栏块增删行有底色且没有删除线与下划线                                                                                                                                        | ✅    |

## 设计要点

- **用 `require` 而不是 `import` 注册语法**：prismjs 的语法文件读取全局 `Prism`，所以全局必须先于它们存在，这些文件要在本模块里按语句顺序 `require`。前端 `package.json` 的 `sideEffects` 只列了 CSS，凡是只为设置全局而存在的模块都会被生产构建丢掉，语法随之什么都不注册、也不报错。Next.js 16.3.0（Turbopack）生产构建里实测：单独的副作用模块写法 bash、diff 都未注册，本模块的写法全部注册。
- **scss 故意不注册**：scss 语法对一行 50,000 字符的 data URI 要 11 秒，而它所继承的 css 只要 1 毫秒，带内联图片的样式表会冻住页面。`EXT_TO_LANGUAGE` 里没有 scss 项，`.scss` 文件按纯文本显示。
- **每行上限对所有语法一视同仁**：41 个语法 × 10 种单行形态实测（Chromium，机器负载很高）：10,000 字符时最慢的是 coffeescript 709 ms、typescript 654 ms、javascript 492 ms（裸 base64），lua 219 ms，css 130 ms（未闭合引号）、111 ms（长引号串），其余不超过 50 ms；100,000 字符时 lua 22 s、css 13 s、markdown 3.4 s，JavaScript 一族在 10,000 字符已超过 400 ms、没有再测更长的。同样的字符切成 80 字符一行后，除 css 外都降到 0.5 s 以内（最慢的是 tsx 的紧凑 JSON，100,000 字符 499 ms）。41 个语法里 13 个随长度超线性增长（JavaScript 一族 9 个、lua、css、markdown、ruby），其余 28 个在 100,000 字符的单行上都不超过 32 ms，病态只出在长行上，所以限制放在行长上。任何一行超过 `MAX_HIGHLIGHT_LINE_CHARS` 就让整份内容保持纯文本。这一条与 Codex TUI（单行 4 KiB）、VS Code（单行 20,000 字符）同样是统一上限，不按语法豁免：bash 在未闭合引号的单行上也是平方增长（100,000 字符 32 ms，400,000 字符 445 ms），豁免名单容易写错，而本机 180,985 个候选文件里会因此改变的只有 67 个（json 40、html 26、yaml 1）。
- **上限的代价**：压缩成一行的合法代码（`.min.css`、`.min.js`、一行的 JSON）超过 10,000 字符就不上色，而这类输入分词很快（压缩成一行的 88,107 字符样式 7 ms）；`TextItemsRenderer` 缩进后的 JSON 里有一段超过 10,000 字符的字符串值时，那一块也不上色，但步骤文本项目前只收到短句（本机 4,504 个最长 456 字符，没有 JSON），碰不到这条路径。上限是预防 base64 一类病态长行的保险：本机 shell 步骤最长一行 348 字符、聊天围栏代码块最长一行 274 字符，都没有触发；391 个含超长行的工作区文件里，大小不超过 100,000 字节的 140 个去掉上限直接分词，最慢 317 ms，没有超过 1 s。
- **上限挡不住的**：css 语法对非 CSS 文本随整份文本平方增长，100,000 字符、80 字符一行的未闭合引号文本 13.3 s；合法样式表不受影响（真实的 `pdf_viewer.css` 100,000 字符 10 ms）。
- **语言名按原样查表**：不做大小写归一化，`Bash` 与未注册的 docker、ini、makefile、powershell 一样按纯文本显示。
- **颜色按对比度换，不换整套配色**：原版 One Light 的注释、字符串、数字在聊天代码块底色（`#f6f6f1`）上分别是 2.38:1、2.96:1、3.79:1，在 diff 删除行的底色上更低（2.19:1、2.73:1、3.49:1）；本产品自己的标准是 4.5:1（`theme-engine/oklch.ts` 的 `meetsContrast` 默认值，主题引擎编译主色时也按它选前景色）。只换不达标的颜色，保留色相与其余颜色，替换值写成 `#rrggbb`，每个值取刚好越过 4.5:1 再留约 0.1 的余量（吸收悬停行的底色变化）。主题引擎只改主色与强调色，不改 `--background`，所以这份静态调色板对用户可选的主题都成立；背景图主题下功能页面的表面不透明度有下限（0.94，`theme-engine/scene-surfaces.ts`），按纯黑（浅色）或纯白（深色）图垫在下面估算，最弱的一对约 4.0:1（浅色注释 4.11:1、深色注释 3.95:1，是计算值，没有在浏览器里复现）。diff 行底色上，深色的红要比其余深色配色浅一档，因为 diff 围栏块里删除行的底色（`rgb(74,42,57)`）比面板亮。
- **4.5:1 保证的范围**：四个 Prism 入口，加上聊天里的行内代码芯片（`lib/constants/codeblock-theme.ts` 的 `INLINE_CODE_CHIP`，真实 Chromium 里浅色 `#ca3500` 对 `#f6f6f1` 4.82:1、深色 `#ff8904` 对 `#1e2939` 6.17:1）。Monaco 编辑器（工作区编辑区、产物代码预览、技能与提示词编辑等 15 处调用点，全部经 `components/features/app-shell/lazy-monaco-editor.tsx`，由它统一给内置的 `vs` / `vs-dark`）用自己的内置主题，不经过本模块。按 `monaco-editor` 0.56.0 的主题规则计算（不含语义 token，没有在浏览器里复现）：工作区编辑区的表面上，浅色 43 个 token 颜色里 7 个低于 4.5:1（HTML/XML 属性名与 SQL 字符串 3.93、annotation 与 metatag 3.88、SQL 运算符 3.58），深色 42 个里 3 个（`variable.predefined` 3.47、pug 的 id 与 class 4.26）；其余编辑器用 Monaco 默认底色（`#fffffe`、`#1e1e1e`），深色有 9 个，最常见的是注释 `#608B4E` 的 4.21:1。出问题的几乎都是少见的 token，关键字、字符串、数字等常见的都达标，所以没有为此自定义 Monaco 主题。

## 模块依赖

- 依赖：`prism-react-renderer`（Prism 实例与主题）、`prismjs`（语法定义，精确固定 1.30.0）；测试读 `theme-engine/oklch.ts` 的 `contrastRatio` 与 `app/globals.css` 的主题变量
- 消费方：
  - `components/features/markdown-render-tools/CodeBlock.tsx`（聊天里的代码块，以及文档预览、看板、技能详情里的 Markdown 代码块；diff 块额外有增删行底色并去掉主题加的删除线与下划线。聊天里的 diff 围栏代码块由 `InlineDiffViewer` 渲染，不走这里）
  - `components/features/message-box/progress-steps/renderers/EnhancedSyntaxHighlighter.tsx`（`CodeRenderer` 的 shell 命令步骤等）
  - `lib/diff/DiffViewer.tsx`（按文件名推断的语言逐行高亮）
  - `components/features/workspace-browser/WorkspaceTextViews.tsx`（只读行号代码视图）
