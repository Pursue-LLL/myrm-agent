/**
 * [INPUT] ./chatExport.ts::ExportData, ExportMessage, ToolSummary, UsageSummary, formatDuration, formatUsd (POS: chat export data and file generation tool).
 * [OUTPUT] buildHtmlDocument.
 * [POS] Markdown-to-HTML export renderer for chat conversations.
 */
import {
  formatDuration,
  formatUsd,
  type AgentInfo,
  type ExportData,
  type ExportMessage,
  type ToolCallDetail,
  type ToolSummary,
  type UsageSummary,
} from './chatExport';
import type { Element, ElementContent } from 'hast';

const VISIBLE_ROLES = new Set(['user', 'assistant']);

const HTML_ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};

function esc(text: string): string {
  return text.replace(/[&<>"']/g, (ch) => HTML_ESCAPE_MAP[ch] ?? ch);
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

interface TokenStats {
  totalPrompt: number;
  totalCompletion: number;
  totalTokens: number;
  messageCount: number;
  userCount: number;
  assistantCount: number;
}

function computeStats(messages: ExportMessage[]): TokenStats {
  const stats: TokenStats = {
    totalPrompt: 0,
    totalCompletion: 0,
    totalTokens: 0,
    messageCount: 0,
    userCount: 0,
    assistantCount: 0,
  };
  for (const msg of messages) {
    if (!VISIBLE_ROLES.has(msg.role)) continue;
    stats.messageCount++;
    if (msg.role === 'user') stats.userCount++;
    else stats.assistantCount++;

    const usage = msg.metadata?.token_usage as
      | { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number }
      | undefined;
    if (usage) {
      stats.totalPrompt += usage.prompt_tokens ?? 0;
      stats.totalCompletion += usage.completion_tokens ?? 0;
      stats.totalTokens += usage.total_tokens ?? 0;
    }
  }
  return stats;
}

function formatTokenCount(n: number): string {
  if (n < 1000) return String(n);
  if (n < 10000) return (n / 1000).toFixed(1) + 'k';
  return Math.round(n / 1000) + 'k';
}

const RESIZE_SCRIPT =
  '<script>new ResizeObserver(function(){parent.postMessage({type:"wh",h:document.documentElement.scrollHeight},"*")}).observe(document.documentElement)</script>';

function renderWidgetIframe(htmlContent: string): string {
  const injected = htmlContent.includes('</body>')
    ? htmlContent.replace('</body>', RESIZE_SCRIPT + '</body>')
    : htmlContent + RESIZE_SCRIPT;
  const escaped = esc(injected);
  return `<div class="widget-container">
<iframe sandbox="allow-scripts" srcdoc="${escaped}" class="widget-iframe" loading="lazy"></iframe>
<details class="widget-source"><summary>Source</summary><pre><code>${esc(htmlContent)}</code></pre></details>
</div>`;
}

interface MarkdownProcessor {
  process(content: string): Promise<{ toString(): string }>;
}

let _processorPromise: Promise<MarkdownProcessor> | null = null;

async function getMarkdownEngine() {
  if (_processorPromise) return _processorPromise;
  _processorPromise = (async () => {
    try {
      const { unified } = await import('unified');
      const { default: remarkParse } = await import('remark-parse');
      const { default: remarkGfm } = await import('remark-gfm');
      const { default: remarkMath } = await import('remark-math');
      const { default: remarkRehype } = await import('remark-rehype');
      const { default: rehypeKatex } = await import('rehype-katex');
      const { default: rehypeHighlight } = await import('rehype-highlight');
      const { default: rehypeStringify } = await import('rehype-stringify');
      const { visit } = await import('unist-util-visit');

      const processor = unified()
        .use(remarkParse)
        .use(remarkGfm)
        .use(remarkMath)
        .use(remarkRehype, { allowDangerousHtml: false })
        .use(rehypeKatex)
        .use(rehypeHighlight)
        .use(() => (tree: Element) => {
          visit(tree, 'element', (node: Element) => {
            if (node.tagName === 'pre' && node.children?.[0]?.type === 'element') {
              const codeNode = node.children[0] as Element;
              if (codeNode.tagName !== 'code') return;

              const lang =
                Array.isArray(codeNode.properties?.className) && typeof codeNode.properties.className[0] === 'string'
                  ? codeNode.properties.className[0].replace('language-', '')
                  : '';

              const textNode = codeNode.children[0];
              const codeText = textNode?.type === 'text' ? textNode.value : '';

              if (lang === 'html' || lang === 'svg') {
                node.tagName = 'div';
                node.properties = { className: ['widget-container'] };
                node.children = [
                  {
                    type: 'raw',
                    value: renderWidgetIframe(codeText),
                  } as unknown as ElementContent,
                ];
                return;
              }

              const langLabel = lang ? `<span class="code-lang">${esc(lang)}</span>` : '';
              node.tagName = 'div';
              node.properties = { className: ['code-block'] };
              node.children = [
                { type: 'raw', value: langLabel } as unknown as ElementContent,
                {
                  type: 'element',
                  tagName: 'pre',
                  properties: {},
                  children: [codeNode],
                } as ElementContent,
              ];
            }
          });
        })
        .use(rehypeStringify, { allowDangerousHtml: true });

      return processor;
    } catch (err) {
      _processorPromise = null;
      throw err;
    }
  })();
  return _processorPromise;
}

async function renderMarkdown(content: string): Promise<string> {
  const processor = await getMarkdownEngine();
  const result = await processor.process(content);
  return String(result);
}

function renderMessageHtml(msg: ExportMessage, renderedContent: string): string {
  if (!VISIBLE_ROLES.has(msg.role)) return '';
  const isUser = msg.role === 'user';
  const roleClass = isUser ? 'user' : 'assistant';
  const roleLabel = isUser ? 'User' : 'Assistant';
  const ts = formatTs(msg.createdAt);

  let sourcesHtml = '';
  const sources = msg.metadata?.sources as
    | Array<{ type?: string; title?: string; url?: string; snippet?: string }>
    | undefined;
  if (sources?.length) {
    sourcesHtml = '<div class="sources"><div class="sources-title">Sources</div><ul>';
    for (const s of sources) {
      const title = esc(s.title || s.url || 'Source');
      const link = s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${title}</a>` : title;
      sourcesHtml += `<li>${link}</li>`;
    }
    sourcesHtml += '</ul></div>';
  }

  return `<div class="message ${roleClass}" id="msg-${esc(msg.createdAt)}">
<div class="msg-header"><span class="role">${roleLabel}</span><span class="timestamp">${ts}</span></div>
<div class="msg-body">${renderedContent}</div>
${sourcesHtml}
</div>`;
}

function getStyles(): string {
  return `
:root{--bg:#fff;--fg:#1a1a1a;--card:#f8f9fa;--card-user:#e8f0fe;--border:#e0e0e0;--muted:#666;--accent:#2563eb;--code-bg:#f5f5f5;--widget-bg:#fafafa;--header-bg:#f0f4f8;--stats-bg:#e8eef6}
[data-theme="dark"]{--bg:#0f0f10;--fg:#e0e0e0;--card:#1a1a1e;--card-user:#1a2333;--border:#2a2a2e;--muted:#888;--accent:#60a5fa;--code-bg:#1e1e22;--widget-bg:#16161a;--header-bg:#14141a;--stats-bg:#1a1a22}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--fg);line-height:1.6;max-width:900px;margin:0 auto;padding:16px}
.export-header{background:var(--header-bg);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:24px}
.export-title{font-size:1.4em;font-weight:700;margin-bottom:4px}
.export-meta{color:var(--muted);font-size:0.85em}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;padding:12px;background:var(--stats-bg);border-radius:8px;font-size:0.85em}
.stat-item{display:flex;gap:4px}.stat-label{color:var(--muted)}.stat-value{font-weight:600}
.theme-toggle{float:right;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer;color:var(--fg);font-size:0.8em}
.message{padding:16px;border:1px solid var(--border);border-radius:10px;margin-bottom:12px}
.message.user{background:var(--card-user)}.message.assistant{background:var(--card)}
.msg-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:0.85em}
.role{font-weight:700;color:var(--accent)}.timestamp{color:var(--muted)}
.msg-body{overflow-wrap:break-word}
.msg-body p{margin:0.5em 0}.msg-body ul,.msg-body ol{padding-left:1.5em;margin:0.5em 0}
.msg-body table{border-collapse:collapse;width:100%;margin:0.5em 0}
.msg-body th,.msg-body td{border:1px solid var(--border);padding:6px 10px;text-align:left}
.msg-body th{background:var(--stats-bg);font-weight:600}
.msg-body blockquote{border-left:3px solid var(--accent);padding-left:12px;color:var(--muted);margin:0.5em 0}
.msg-body a{color:var(--accent);text-decoration:none}.msg-body a:hover{text-decoration:underline}
.msg-body img{max-width:100%;border-radius:8px;margin:0.5em 0}
.code-block{position:relative;margin:0.8em 0;border-radius:8px;overflow:hidden;background:var(--code-bg)}
.code-lang{position:absolute;top:6px;right:10px;font-size:0.7em;color:var(--muted);text-transform:uppercase}
.code-block pre{margin:0;padding:14px;overflow-x:auto;font-size:0.88em;line-height:1.5}
.code-block code{font-family:"SF Mono",Menlo,Monaco,"Courier New",monospace}
.msg-body code:not(.hljs){background:var(--code-bg);padding:2px 5px;border-radius:4px;font-size:0.9em;font-family:"SF Mono",Menlo,Monaco,"Courier New",monospace}
.widget-container{margin:0.8em 0;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.widget-iframe{width:100%;min-height:200px;max-height:600px;border:none;background:var(--widget-bg)}
.widget-source{padding:4px 10px;font-size:0.75em;color:var(--muted);border-top:1px solid var(--border)}
.widget-source summary{cursor:pointer;padding:4px 0}
.widget-source pre{margin:4px 0;max-height:200px;overflow:auto;font-size:0.85em;background:var(--code-bg);padding:8px;border-radius:4px}
.sources{margin-top:10px;padding:10px;background:var(--stats-bg);border-radius:8px;font-size:0.85em}
.sources-title{font-weight:600;margin-bottom:4px;color:var(--muted)}.sources ul{padding-left:1.2em;margin:0}
.sources li{margin:2px 0}.sources a{color:var(--accent)}
.tool-activity{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px}
.tool-activity-title{font-weight:700;font-size:0.95em;margin-bottom:10px;color:var(--fg)}
.tool-table{width:100%;border-collapse:collapse;font-size:0.85em}
.tool-table th{text-align:left;padding:6px 10px;border-bottom:2px solid var(--border);color:var(--muted);font-weight:600}
.tool-table td{padding:6px 10px;border-bottom:1px solid var(--border)}
.tool-table tr:last-child td{border-bottom:none;font-weight:700}
.tool-table .tool-name{font-family:"SF Mono",Menlo,Monaco,"Courier New",monospace;font-size:0.9em}
.agent-card{display:flex;align-items:center;gap:12px;margin-top:12px;padding:10px 14px;background:var(--stats-bg);border-radius:8px;font-size:0.88em}
.agent-card .agent-name{font-weight:700;color:var(--fg)}.agent-card .agent-model{background:var(--accent);color:#fff;padding:2px 8px;border-radius:4px;font-size:0.78em;font-weight:600}
.agent-card .agent-desc{color:var(--muted);font-size:0.85em;margin-top:2px}
.tool-details{margin-top:8px;font-size:0.82em}
.tool-details summary{cursor:pointer;color:var(--muted);padding:4px 0;font-weight:600}
.tool-details summary:hover{color:var(--fg)}
.tool-details ul{list-style:none;padding:6px 0 0 12px;margin:0;border-left:2px solid var(--border)}
.tool-details li{padding:3px 0;color:var(--fg);font-family:"SF Mono",Menlo,Monaco,"Courier New",monospace;font-size:0.92em}
.tool-details .tool-dur{color:var(--muted);font-size:0.9em}
.footer{text-align:center;padding:20px;color:var(--muted);font-size:0.8em;border-top:1px solid var(--border);margin-top:24px}
@media(max-width:640px){body{padding:8px}.export-header{padding:14px}.message{padding:12px}.stats{flex-direction:column;gap:6px}}
@media print{.theme-toggle{display:none}.widget-source{display:none}.code-block,.message{break-inside:avoid}body{max-width:none;padding:0}}
`;
}

function getHljsTheme(): string {
  return `
.hljs{color:var(--fg);background:transparent}
.hljs-keyword,.hljs-selector-tag,.hljs-literal,.hljs-section,.hljs-link{color:#d73a49}
[data-theme="dark"] .hljs-keyword,[data-theme="dark"] .hljs-selector-tag,[data-theme="dark"] .hljs-literal,[data-theme="dark"] .hljs-section,[data-theme="dark"] .hljs-link{color:#ff7b72}
.hljs-string,.hljs-title,.hljs-name,.hljs-type,.hljs-attribute,.hljs-symbol,.hljs-bullet,.hljs-addition,.hljs-variable,.hljs-template-tag,.hljs-template-variable{color:#032f62}
[data-theme="dark"] .hljs-string,[data-theme="dark"] .hljs-title,[data-theme="dark"] .hljs-name,[data-theme="dark"] .hljs-type,[data-theme="dark"] .hljs-attribute,[data-theme="dark"] .hljs-symbol,[data-theme="dark"] .hljs-bullet,[data-theme="dark"] .hljs-addition,[data-theme="dark"] .hljs-variable,[data-theme="dark"] .hljs-template-tag,[data-theme="dark"] .hljs-template-variable{color:#a5d6ff}
.hljs-comment,.hljs-quote,.hljs-deletion,.hljs-meta{color:#6a737d}
[data-theme="dark"] .hljs-comment,[data-theme="dark"] .hljs-quote,[data-theme="dark"] .hljs-deletion,[data-theme="dark"] .hljs-meta{color:#8b949e}
.hljs-number,.hljs-regexp,.hljs-tag .hljs-attr,.hljs-selector-id,.hljs-selector-class{color:#005cc5}
[data-theme="dark"] .hljs-number,[data-theme="dark"] .hljs-regexp,[data-theme="dark"] .hljs-tag .hljs-attr,[data-theme="dark"] .hljs-selector-id,[data-theme="dark"] .hljs-selector-class{color:#79c0ff}
.hljs-built_in,.hljs-builtin-name{color:#e36209}
[data-theme="dark"] .hljs-built_in,[data-theme="dark"] .hljs-builtin-name{color:#ffa657}
`;
}

function getInteractiveJs(): string {
  return `
(function(){
  var t=document.getElementById('theme-toggle');
  var root=document.documentElement;
  t.addEventListener('click',function(){
    var d=root.getAttribute('data-theme')==='dark'?'light':'dark';
    root.setAttribute('data-theme',d);
    t.textContent=d==='dark'?'\\u2600 Light':'\\u263E Dark';
  });
  window.addEventListener('message',function(e){
    if(!e.data||e.data.type!=='wh'||typeof e.data.h!=='number')return;
    document.querySelectorAll('.widget-iframe').forEach(function(f){
      if(f.contentWindow===e.source){
        f.style.height=Math.min(Math.max(e.data.h,100),600)+'px';
      }
    });
  });
})();
`;
}

interface HtmlLabels {
  msgs: string;
  user: string;
  asst: string;
  tokens: string;
  input: string;
  output: string;
  exported: string;
  toolActivity: string;
  tool: string;
  calls: string;
  duration: string;
  total: string;
  apiCalls: string;
  cost: string;
}

function getLabels(lang: 'en' | 'zh'): HtmlLabels {
  return lang === 'zh'
    ? {
        msgs: '消息',
        user: '用户',
        asst: '助手',
        tokens: 'Tokens',
        input: '输入',
        output: '输出',
        exported: '导出自 Myrm',
        toolActivity: '工具调用',
        tool: '工具',
        calls: '调用次数',
        duration: '耗时',
        total: '总计',
        apiCalls: 'API 调用',
        cost: '费用',
      }
    : {
        msgs: 'Messages',
        user: 'User',
        asst: 'Assistant',
        tokens: 'Tokens',
        input: 'Input',
        output: 'Output',
        exported: 'Exported from Myrm',
        toolActivity: 'Tool Activity',
        tool: 'Tool',
        calls: 'Calls',
        duration: 'Duration',
        total: 'Total',
        apiCalls: 'API Calls',
        cost: 'Cost',
      };
}

function renderUsageStats(usage: UsageSummary | null | undefined, labels: HtmlLabels): string {
  if (!usage || (usage.totalCalls === 0 && usage.totalTokens === 0)) return '';
  const parts: string[] = [];
  if (usage.totalCalls > 0) {
    parts.push(
      `<div class="stat-item"><span class="stat-label">${labels.apiCalls}:</span><span class="stat-value">${usage.totalCalls}</span></div>`,
    );
  }
  if (usage.totalUsd > 0) {
    parts.push(
      `<div class="stat-item"><span class="stat-label">${labels.cost}:</span><span class="stat-value">${formatUsd(usage.totalUsd)}</span></div>`,
    );
  }
  return parts.join('\n');
}

function renderToolActivityHtml(tools: ToolSummary | null | undefined, labels: HtmlLabels): string {
  if (!tools || tools.toolsUsed.length === 0) return '';
  let rows = '';
  for (const t of tools.toolsUsed) {
    rows += `<tr><td class="tool-name">${esc(t.name)}</td><td>${t.count}</td><td>${formatDuration(t.totalMs)}</td></tr>`;
  }
  rows += `<tr><td><strong>${labels.total}</strong></td><td><strong>${tools.totalToolCalls}</strong></td><td><strong>${formatDuration(tools.totalDurationMs)}</strong></td></tr>`;

  return `<div class="tool-activity">
<div class="tool-activity-title">${labels.toolActivity}</div>
<table class="tool-table">
<thead><tr><th>${labels.tool}</th><th>${labels.calls}</th><th>${labels.duration}</th></tr></thead>
<tbody>${rows}</tbody>
</table>
</div>`;
}

function renderAgentCard(agent: AgentInfo | null | undefined, labels: HtmlLabels): string {
  if (!agent) return '';
  const modelBadge = agent.model ? `<span class="agent-model">${esc(agent.model)}</span>` : '';
  const desc = agent.description ? `<div class="agent-desc">${esc(agent.description)}</div>` : '';
  return `<div class="agent-card">
<div><span class="agent-name">${esc(agent.name)}</span> ${modelBadge}${desc}</div>
</div>`;
}

function renderToolCallDetailsHtml(
  details: ToolCallDetail[] | null | undefined,
  turnIndex: number,
  labels: HtmlLabels,
): string {
  if (!details || details.length === 0) return '';
  const turnCalls = details.filter((d) => d.turnIndex === turnIndex);
  if (turnCalls.length === 0) return '';

  const totalMs = turnCalls.reduce((sum, d) => sum + (d.durationMs ?? 0), 0);
  let items = '';
  for (const tc of turnCalls) {
    const dur = tc.durationMs != null ? ` <span class="tool-dur">${formatDuration(tc.durationMs)}</span>` : '';
    const args = tc.argsSummary ? `(${esc(tc.argsSummary)})` : '';
    items += `<li>${esc(tc.name)}${args}${dur}</li>`;
  }

  return `<details class="tool-details">
<summary>${turnCalls.length} ${labels.toolActivity} (${formatDuration(totalMs)})</summary>
<ul>${items}</ul>
</details>`;
}

export async function buildHtmlDocument(
  data: ExportData,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
): Promise<string> {
  const title = data.chat.title || 'Untitled';
  const stats = computeStats(data.messages);
  const exportDate = new Date().toLocaleString();
  const labels = getLabels(lang);

  const renderedMessages: string[] = [];
  let assistantTurnIndex = 0;
  for (const msg of data.messages) {
    if (!VISIBLE_ROLES.has(msg.role)) continue;
    const htmlContent = await renderMarkdown(msg.content);
    let msgHtml = renderMessageHtml(msg, htmlContent);
    if (msg.role === 'assistant') {
      if (data.toolCallDetails) {
        const toolDetailsHtml = renderToolCallDetailsHtml(data.toolCallDetails, assistantTurnIndex, labels);
        if (toolDetailsHtml) {
          const lastClose = msgHtml.lastIndexOf('</div>');
          msgHtml = msgHtml.slice(0, lastClose) + toolDetailsHtml + '\n</div>';
        }
      }
      assistantTurnIndex++;
    }
    renderedMessages.push(msgHtml);
  }

  const themeToggleText = theme === 'dark' ? '☀ Light' : '☾ Dark';
  const usageHtml = renderUsageStats(data.usageSummary, labels);
  const toolActivityHtml = renderToolActivityHtml(data.toolSummary, labels);
  const agentCardHtml = renderAgentCard(data.agentInfo, labels);

  return `<!DOCTYPE html>
<html lang="${lang}" data-theme="${theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} - Myrm</title>
<style>${getStyles()}${getHljsTheme()}</style>
</head>
<body>
<div class="export-header">
<button class="theme-toggle" id="theme-toggle">${themeToggleText}</button>
<div class="export-title">${esc(title)}</div>
<div class="export-meta">${labels.exported} · ${exportDate}</div>
${agentCardHtml}
<div class="stats">
<div class="stat-item"><span class="stat-label">${labels.msgs}:</span><span class="stat-value">${stats.messageCount}</span></div>
<div class="stat-item"><span class="stat-label">${labels.user}:</span><span class="stat-value">${stats.userCount}</span></div>
<div class="stat-item"><span class="stat-label">${labels.asst}:</span><span class="stat-value">${stats.assistantCount}</span></div>
${
  stats.totalTokens > 0
    ? `<div class="stat-item"><span class="stat-label">${labels.tokens}:</span><span class="stat-value">${formatTokenCount(stats.totalTokens)}</span></div>
<div class="stat-item"><span class="stat-label">${labels.input}:</span><span class="stat-value">${formatTokenCount(stats.totalPrompt)}</span></div>
<div class="stat-item"><span class="stat-label">${labels.output}:</span><span class="stat-value">${formatTokenCount(stats.totalCompletion)}</span></div>`
    : ''
}
${usageHtml}
</div>
</div>
${toolActivityHtml}
${renderedMessages.join('\n')}
<div class="footer">${labels.exported} · ${exportDate}</div>
<script>${getInteractiveJs()}</script>
</body>
</html>`;
}
