# lib/syntax/

代码高亮的共享注册表。`prism-react-renderer` 自带的 Prism 只有 28 种语法，产品里却到处用到它没有的语言：shell 命令步骤用 `bash`、聊天里的 ```diff 代码块、文件按扩展名推断出的 java / ruby / toml 等。四个高亮入口经这一个模块取得 Prism 与语言判定，不再各自碰 `prism-react-renderer` 的语法表。

## 文件

| 文件                                 | 职责                                                                                                                                                                                                                                                                  |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `prism.ts`                           | 注册 bash（含 sh、shell，另把 zsh 指向同一份）、diff、java、ruby、csharp、toml、lua、r、php、dart；导出 `Prism`、`MAX_HIGHLIGHT_LINE_CHARS`（10,000）与 `resolveLanguage(language, code?)`：语言没有语法、或代码里有一行超过上限时返回 `text`，否则原样返回语言名     |
| `__tests__/prism.test.ts`            | 每种新语法能识别各自的代码片段、`sh/shell/zsh` 别名、原有语法保留、`resolveLanguage` 的名字与长行判定（恰好等于上限不拦、多一个字符才拦、CRLF 与首行同样生效）；`EXT_TO_LANGUAGE` 里的每个语言都必须能被 `resolveLanguage` 原样解析，增删语法或映射时两边对不上就失败 |
| `__tests__/grammarSurfaces.test.tsx` | 四个真实入口（`CodeBlock`、`EnhancedSyntaxHighlighter`、`DiffViewer`、`LineNumberedCode`）里 bash 的关键字确实带上主题色，长行文件在四处都保持无色；```diff 块的增删行有底色且没有删除线与下划线                                                                      |

## 设计要点

- **用 `require` 而不是 `import` 注册语法**：prismjs 的语法文件读取全局 `Prism`，所以全局必须先于它们存在。这些文件要在本模块里按语句顺序 `require`。前端 `package.json` 的 `sideEffects` 只列了 CSS，凡是只为设置全局而存在的模块都会被生产构建丢掉，语法随之什么都不注册、也不报错。在 Next.js 16.3.0（Turbopack）的生产构建里实测：单独的副作用模块写法 `bash`、`diff` 都未注册，本模块的写法全部注册。
- **scss 故意不注册**：scss 语法对一行 50,000 字符的 data URI 要 11 秒，而它所继承的 css 只要 1 毫秒，带内联图片的样式表会冻住页面。`EXT_TO_LANGUAGE` 里没有 scss 项，`.scss` 文件按纯文本显示。
- **每行上限**：markdown 语法对 base64 长行 10K / 50K / 100K 字符分别耗时 36 ms / 0.85 s / 3.5 s，css 语法对未闭合引号的长行更久。任何一行超过 `MAX_HIGHLIGHT_LINE_CHARS` 就让整份内容保持纯文本；上限处最坏耗时 133 ms（Chromium）/ 286 ms（WebKit）。
- **语言名按原样查表**：不做大小写归一化，`Bash` 与未注册的 docker、ini、makefile、powershell 一样按纯文本显示。

## 消费方

- `components/features/markdown-render-tools/CodeBlock.tsx`（聊天代码块；```diff 块额外去掉主题加的删除线与下划线）
- `components/features/message-box/progress-steps/renderers/EnhancedSyntaxHighlighter.tsx`（`CodeRenderer` 的 shell 命令步骤等）
- `lib/diff/DiffViewer.tsx`（按文件名推断的语言逐行高亮）
- `components/features/workspace-browser/WorkspaceTextViews.tsx`（只读行号代码视图）
