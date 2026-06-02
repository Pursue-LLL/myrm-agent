import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import type { Message, Source } from '@/store/chat/types';
/**
 * [INPUT] 聊天详情页与聊天列表传入的导出数据；Message 用于单条消息导出。
 * [OUTPUT] ExportMessage, ExportChat, ExportData, formatChatAsMarkdown, formatChatAsJson,
 *          downloadAsMarkdown, downloadAsJson, downloadAsHtml, copyAsMarkdown,
 *          downloadMessageAsMarkdown, downloadMessageAsDocx, downloadMessageAsHtml, downloadMessageAsImage.
 * [POS] 聊天导出数据与文件生成工具（聊天级 + 单条消息级）。
 */
export interface ExportMessage {
  role: string;
  content: string;
  createdAt: string;
  metadata: Record<string, unknown>;
}

export interface ExportChat {
  id: string;
  title: string | null;
  source: string;
  createdAt: string;
}

export interface ToolUsageEntry {
  name: string;
  count: number;
  totalMs: number;
}

export interface ToolSummary {
  totalToolCalls: number;
  totalDurationMs: number;
  toolsUsed: ToolUsageEntry[];
}

export interface UsageSummary {
  totalCalls: number;
  totalTokens: number;
  totalUsd: number;
}

export interface ExportData {
  chat: ExportChat;
  messages: ExportMessage[];
  toolSummary?: ToolSummary | null;
  usageSummary?: UsageSummary | null;
}

const VISIBLE_ROLES = new Set(['user', 'assistant']);

function sanitizeFilename(name: string): string {
  // eslint-disable-next-line no-control-regex
  return name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').trim() || 'Untitled';
}

function buildFilename(title: string | null, ext: string): string {
  const safe = sanitizeFilename(title || 'Untitled');
  const date = new Date().toISOString().slice(0, 10);
  return `${safe}-${date}.${ext}`;
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

function formatTokenCount(n: number): string {
  if (n < 1000) return String(n);
  if (n < 10_000) return (n / 1000).toFixed(1) + 'k';
  return Math.round(n / 1000) + 'k';
}

export function formatUsd(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

function buildSummarySection(data: ExportData): string[] {
  const lines: string[] = [];

  const usage = data.usageSummary;
  if (usage && (usage.totalCalls > 0 || usage.totalTokens > 0)) {
    lines.push('## Session Summary', '');
    if (usage.totalCalls > 0) lines.push(`- **API Calls**: ${usage.totalCalls}`);
    if (usage.totalTokens > 0) lines.push(`- **Tokens**: ${formatTokenCount(usage.totalTokens)}`);
    if (usage.totalUsd > 0) lines.push(`- **Cost**: ${formatUsd(usage.totalUsd)}`);
    lines.push('');
  }

  const tools = data.toolSummary;
  if (tools && tools.toolsUsed.length > 0) {
    lines.push('## Tool Activity', '');
    lines.push('| Tool | Calls | Duration |');
    lines.push('|------|-------|----------|');
    for (const t of tools.toolsUsed) {
      lines.push(`| ${t.name} | ${t.count} | ${formatDuration(t.totalMs)} |`);
    }
    lines.push(`| **Total** | **${tools.totalToolCalls}** | **${formatDuration(tools.totalDurationMs)}** |`);
    lines.push('');
  }

  if (lines.length > 0) {
    lines.push('---', '');
  }

  return lines;
}

export function formatChatAsMarkdown(data: ExportData): string {
  const title = data.chat.title || 'Untitled';
  const lines: string[] = [`# ${title}`, '', `> Exported from Myrm · ${new Date().toLocaleString()}`, '', '---', ''];

  lines.push(...buildSummarySection(data));

  for (const msg of data.messages) {
    if (!VISIBLE_ROLES.has(msg.role)) continue;
    const role = msg.role === 'user' ? 'User' : 'Assistant';
    lines.push(`**${role}** · ${formatTimestamp(msg.createdAt)}`);
    lines.push('');
    const reasoning = (msg.metadata?.reasoning_content ?? msg.metadata?.reasoning) as string | undefined;
    if (reasoning) {
      lines.push('<details>', '<summary>Thinking</summary>', '', reasoning, '', '</details>', '');
    }
    lines.push(msg.content);
    lines.push('');
    lines.push('---');
    lines.push('');
  }

  return lines.join('\n');
}

export function formatChatAsJson(data: ExportData): string {
  return JSON.stringify(
    {
      title: data.chat.title,
      source: data.chat.source,
      exportedAt: new Date().toISOString(),
      messages: data.messages,
      ...(data.usageSummary ? { usageSummary: data.usageSummary } : {}),
      ...(data.toolSummary ? { toolSummary: data.toolSummary } : {}),
    },
    null,
    2,
  );
}

export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function downloadAsMarkdown(data: ExportData): void {
  const content = formatChatAsMarkdown(data);
  downloadFile(content, buildFilename(data.chat.title, 'md'), 'text/markdown;charset=utf-8');
}

export function downloadAsJson(data: ExportData): void {
  const content = formatChatAsJson(data);
  downloadFile(content, buildFilename(data.chat.title, 'json'), 'application/json;charset=utf-8');
}

export async function downloadAsHtml(
  data: ExportData,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
): Promise<void> {
  const { buildHtmlDocument } = await import('./chatExportHtml');
  const html = await buildHtmlDocument(data, theme, lang);
  downloadFile(html, buildFilename(data.chat.title, 'html'), 'text/html;charset=utf-8');
}

export async function copyAsMarkdown(data: ExportData): Promise<void> {
  const content = formatChatAsMarkdown(data);
  try {
    await writeToClipboard(content);
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = content;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
}

// ---------------------------------------------------------------------------
// 单条消息导出
// ---------------------------------------------------------------------------

function downloadBlobFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function formatSourcesFootnotes(sources?: Source[]): string {
  if (!sources || sources.length === 0) return '';
  const lines = sources.map((s, i) => `[${i + 1}] ${s.url || s.title || 'Unknown source'}`);
  return `\n\nCitations:\n${lines.join('\n')}`;
}

function formatMessageMarkdown(message: Message, includeReasoning: boolean): string {
  const lines: string[] = [];
  if (includeReasoning && message.reasoning) {
    lines.push('<details>', '<summary>Thinking</summary>', '', message.reasoning, '', '</details>', '');
  }
  lines.push(message.content);
  lines.push(formatSourcesFootnotes(message.sources));
  return lines.join('\n').trim();
}

function extractMessageTitle(content: string): string {
  return content.split('\n')[0]?.slice(0, 80) || 'message';
}

function buildSingleMessageExportData(message: Message, markdown: string): ExportData {
  const ts = message.createdAt?.toISOString?.() ?? new Date().toISOString();
  return {
    chat: { id: message.chatId, title: null, source: 'myrm', createdAt: ts },
    messages: [{ role: message.role, content: markdown, createdAt: ts, metadata: {} }],
  };
}

export function downloadMessageAsMarkdown(message: Message, includeReasoning: boolean): void {
  const content = formatMessageMarkdown(message, includeReasoning);
  downloadFile(content, buildFilename(extractMessageTitle(message.content), 'md'), 'text/markdown;charset=utf-8');
}

export async function downloadMessageAsHtml(
  message: Message,
  includeReasoning: boolean,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
): Promise<void> {
  const markdown = formatMessageMarkdown(message, includeReasoning);
  const { buildHtmlDocument } = await import('./chatExportHtml');
  const html = await buildHtmlDocument(buildSingleMessageExportData(message, markdown), theme, lang);
  downloadFile(html, buildFilename(extractMessageTitle(message.content), 'html'), 'text/html;charset=utf-8');
}

export async function downloadMessageAsDocx(message: Message, includeReasoning: boolean): Promise<void> {
  const markdown = formatMessageMarkdown(message, includeReasoning);
  const { buildHtmlDocument } = await import('./chatExportHtml');
  const html = await buildHtmlDocument(buildSingleMessageExportData(message, markdown), 'light', 'en');
  const { toDocx } = await import('docshift');
  const docxBlob = await toDocx(html);
  downloadBlobFile(docxBlob, buildFilename(extractMessageTitle(message.content), 'docx'));
}

export async function downloadMessageAsImage(element: HTMLElement, message: Message): Promise<void> {
  const { default: html2canvas } = await import('html2canvas');
  const canvas = await html2canvas(element, {
    useCORS: true,
    backgroundColor: null,
    scale: 2,
  });
  return new Promise<void>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('Failed to create image blob'));
        return;
      }
      downloadBlobFile(blob, buildFilename(extractMessageTitle(message.content), 'png'));
      resolve();
    }, 'image/png');
  });
}
