/**
 * [INPUT] ./chatExport.ts::ExportData, ExportFormatOptions, ExportMessage; ./chatExportHtmlTemplates.ts::esc, getStyles, getHljsTheme, getInteractiveJs, getLabels, renderUsageStats, renderToolActivityHtml, renderAgentCard, renderToolCallDetailsHtml.
 * [OUTPUT] buildHtmlDocument.
 * [POS] Markdown-to-HTML export renderer for chat conversations.
 */
import type { ExportData, ExportFormatOptions, ExportMessage } from './chatExport';
import {
  esc,
  getStyles,
  getHljsTheme,
  getInteractiveJs,
  getLabels,
  renderUsageStats,
  renderToolActivityHtml,
  renderAgentCard,
  renderToolCallDetailsHtml,
} from './chatExportHtmlTemplates';
import type { Element, ElementContent } from 'hast';

const VISIBLE_ROLES = new Set(['user', 'assistant']);

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
    if (!VISIBLE_ROLES.has(msg.role)) {
      continue;
    }
    stats.messageCount++;
    if (msg.role === 'user') {
      stats.userCount++;
    } else {
      stats.assistantCount++;
    }

    const usage = msg.metadata?.token_usage as
      { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | undefined;
    if (usage) {
      stats.totalPrompt += usage.prompt_tokens ?? 0;
      stats.totalCompletion += usage.completion_tokens ?? 0;
      stats.totalTokens += usage.total_tokens ?? 0;
    }
  }
  return stats;
}

function formatTokenCount(n: number): string {
  if (n < 1000) {
    return String(n);
  }
  if (n < 10000) {
    return (n / 1000).toFixed(1) + 'k';
  }
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
  if (_processorPromise) {
    return _processorPromise;
  }
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
      const { visit, SKIP } = await import('unist-util-visit');

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
              if (codeNode.tagName !== 'code') {
                return;
              }

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
                return SKIP;
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
              return SKIP;
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
  if (!VISIBLE_ROLES.has(msg.role)) {
    return '';
  }
  const isUser = msg.role === 'user';
  const roleClass = isUser ? 'user' : 'assistant';
  const roleLabel = isUser ? 'User' : 'Assistant';
  const ts = formatTs(msg.createdAt);

  let sourcesHtml = '';
  const sources = msg.metadata?.sources as
    Array<{ type?: string; title?: string; url?: string; snippet?: string }> | undefined;
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

export async function buildHtmlDocument(
  data: ExportData,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
  options?: ExportFormatOptions,
): Promise<string> {
  const includeReasoning = options?.includeReasoning ?? true;
  const includeToolCalls = options?.includeToolCalls ?? true;
  const title = data.chat.title || 'Untitled';
  const stats = computeStats(data.messages);
  const exportDate = new Date().toLocaleString();
  const labels = getLabels(lang);

  const renderedMessages: string[] = [];
  let assistantTurnIndex = 0;
  for (const msg of data.messages) {
    if (!VISIBLE_ROLES.has(msg.role)) {
      continue;
    }
    const htmlContent = await renderMarkdown(msg.content);
    let msgHtml = renderMessageHtml(msg, htmlContent);

    if (includeReasoning) {
      const reasoning = (msg.metadata?.reasoning_content ?? msg.metadata?.reasoning) as string | undefined;
      if (reasoning) {
        const thinkingHtml = `<details class="thinking-block"><summary>${esc(labels.thinking)}</summary><div class="thinking-content">${esc(reasoning)}</div></details>\n`;
        const bodyIdx = msgHtml.indexOf('<div class="msg-body">');
        if (bodyIdx !== -1) {
          msgHtml = msgHtml.slice(0, bodyIdx) + thinkingHtml + msgHtml.slice(bodyIdx);
        }
      }
    }

    if (msg.role === 'assistant') {
      if (includeToolCalls && data.toolCallDetails) {
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

  const themeToggleText = theme === 'dark' ? 'Light' : 'Dark';
  const usageHtml = renderUsageStats(data.usageSummary, labels);
  const toolActivityHtml = includeToolCalls ? renderToolActivityHtml(data.toolSummary, labels) : '';
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
${data.redacted ? `<div class="redacted-notice">${lang === 'zh' ? '[Security] 本会话已启用敏感凭据自动脱敏安全保护' : '[Security] Sensitive secrets and credentials have been automatically redacted.'}</div>` : ''}
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
