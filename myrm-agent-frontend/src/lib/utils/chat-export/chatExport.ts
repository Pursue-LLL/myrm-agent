import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { sanitizeFilename, triggerDownload } from '@/lib/utils/fileUtils';
import { defaultLocale } from '@/i18n/config';
import { redactSensitiveClientText } from '@/lib/utils/error-handling';
import { getClientLocale, parseLocaleQueryParam } from '@/lib/utils/locale';
import type { Message } from '@/store/chat/types';
import {
  extractMessageTitle,
  formatMessageMarkdown,
  formatReasoning,
  type MessageLabels,
} from './chatExportMessageText';
import { printHtmlDocument } from './printHtmlDocument';
/**
 * [INPUT] 聊天详情页与聊天列表传入的导出数据；Message 用于单条消息导出。
 *         fileUtils::sanitizeFilename (POS: 通用文件工具 — 文件名非法字符清理)；
 *         fileUtils::triggerDownload (POS: 通用文件工具 — 文件下载，Web a[download] / Tauri 系统保存对话框)；
 *         error-handling::redactSensitiveClientText (POS: 客户端轻量敏感凭据脱敏清洗工具 — OpenAI/GitHub/AWS/私钥/JWT/URL 查询串凭据/密钥对脱敏，CWE-312 防护)；
 *         locale::getClientLocale, parseLocaleQueryParam; i18n/config::defaultLocale (POS: 界面语言 — 客户端读取并校验 NEXT_LOCALE cookie，缺省回退与服务端一致)；
 *         chatExportMessageText::formatMessageMarkdown, extractMessageTitle, formatReasoning, MessageLabels (POS: 单条消息导出文本 — Markdown 排版（思考链、来源；标签措辞由调用方给出）与文件名标题)；
 *         printHtmlDocument::printHtmlDocument (POS: 隐藏 iframe 打印导出文档，等内嵌字体就绪后再调起打印)。
 * [OUTPUT] Types: ExportMessage, ExportChat, ExportData, ToolUsageEntry, ToolSummary,
 *          UsageSummary, AgentInfo, ToolCallDetail, ExportFormatOptions;
 *          formatChatAsMarkdown, formatChatAsJson, downloadFile, getExportLang,
 *          downloadAsMarkdown, downloadAsJson, downloadAsHtml, copyAsMarkdown, printChat,
 *          downloadMessageAsMarkdown, downloadMessageAsDocx, downloadMessageAsHtml, downloadMessageAsImage;
 *          formatDuration, formatUsd (package-internal: consumed by chatExportHtmlTemplates).
 * [POS] 聊天导出数据与文件生成工具（聊天级 + 单条消息级 + 打印）。
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

export interface AgentInfo {
  name: string;
  model: string | null;
  description: string | null;
}

export interface ToolCallDetail {
  turnIndex: number;
  name: string;
  argsSummary: string;
  durationMs: number | null;
  success: boolean;
}

export interface ExportData {
  chat: ExportChat;
  messages: ExportMessage[];
  toolSummary?: ToolSummary | null;
  usageSummary?: UsageSummary | null;
  agentInfo?: AgentInfo | null;
  toolCallDetails?: ToolCallDetail[] | null;
  redacted?: boolean;
}

const VISIBLE_ROLES = new Set(['user', 'assistant']);

// The session transcript is English throughout (headings, roles, summary), so its reasoning label is too; only the
// single-message exports take their labels from the caller.
const TRANSCRIPT_REASONING_LABEL = 'Reasoning';

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
  if (ms < 1000) {
    return `${ms}ms`;
  }
  if (ms < 60_000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  return `${(ms / 60_000).toFixed(1)}m`;
}

function formatTokenCount(n: number): string {
  if (n < 1000) {
    return String(n);
  }
  if (n < 10_000) {
    return `${(n / 1000).toFixed(1)}k`;
  }
  return `${Math.round(n / 1000)}k`;
}

export function formatUsd(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

function buildSummarySection(data: ExportData): string[] {
  const lines: string[] = [];
  const usage = data.usageSummary;
  if (usage && (usage.totalCalls > 0 || usage.totalTokens > 0)) {
    lines.push('## Session Summary', '');
    if (usage.totalCalls > 0) {
      lines.push(`- **API Calls**: ${usage.totalCalls}`);
    }
    if (usage.totalTokens > 0) {
      lines.push(`- **Tokens**: ${formatTokenCount(usage.totalTokens)}`);
    }
    if (usage.totalUsd > 0) {
      lines.push(`- **Cost**: ${formatUsd(usage.totalUsd)}`);
    }
    lines.push('');
  }

  const tools = data.toolSummary;
  if (tools && tools.toolsUsed.length > 0) {
    lines.push('## Tool Activity', '', '| Tool | Calls | Duration |', '|------|-------|----------|');
    for (const t of tools.toolsUsed) {
      lines.push(`| ${t.name} | ${t.count} | ${formatDuration(t.totalMs)} |`);
    }
    lines.push(`| **Total** | **${tools.totalToolCalls}** | **${formatDuration(tools.totalDurationMs)}** |`, '');
  }

  if (lines.length > 0) {
    lines.push('---', '');
  }
  return lines;
}

export interface ExportFormatOptions {
  includeReasoning?: boolean;
  includeToolCalls?: boolean;
}

export function formatChatAsMarkdown(data: ExportData, options?: ExportFormatOptions): string {
  const includeReasoning = options?.includeReasoning ?? true;
  const includeToolCalls = options?.includeToolCalls ?? true;
  const title = data.chat.title || 'Untitled';
  const lines: string[] = [`# ${title}`, '', `> Exported from Myrm · ${new Date().toLocaleString()}`, ''];

  if (data.redacted) {
    lines.push('> [Security] Sensitive secrets and credentials have been automatically redacted.', '');
  }

  if (data.agentInfo) {
    const a = data.agentInfo;
    const parts = [`> **Agent**: ${a.name}`];
    if (a.model) {
      parts.push(`· Model: ${a.model}`);
    }
    lines.push(parts.join(' '));
    if (a.description) {
      lines.push(`> ${a.description}`);
    }
    lines.push('');
  }

  lines.push('---', '');
  if (includeToolCalls) {
    lines.push(...buildSummarySection(data));
  }

  let mdTurnIndex = 0;
  for (const msg of data.messages) {
    if (!VISIBLE_ROLES.has(msg.role)) {
      continue;
    }
    const role = msg.role === 'user' ? 'User' : 'Assistant';
    lines.push(`**${role}** · ${formatTimestamp(msg.createdAt)}`);
    lines.push('');
    if (includeReasoning) {
      const reasoning = (msg.metadata?.reasoning_content ?? msg.metadata?.reasoning) as string | undefined;
      if (reasoning) {
        lines.push(...formatReasoning(reasoning, 'fold', TRANSCRIPT_REASONING_LABEL));
      }
    }
    lines.push(msg.content);
    lines.push('');
    if (includeToolCalls && msg.role === 'assistant' && data.toolCallDetails) {
      const turnCalls = data.toolCallDetails.filter((d) => d.turnIndex === mdTurnIndex);
      if (turnCalls.length > 0) {
        const totalMs = turnCalls.reduce((s, d) => s + (d.durationMs ?? 0), 0);
        lines.push('<details>', `<summary>${turnCalls.length} tool calls (${formatDuration(totalMs)})</summary>`, '');
        for (const tc of turnCalls) {
          const mark = tc.success ? '+' : 'x';
          const dur = tc.durationMs !== null ? ` ${formatDuration(tc.durationMs)}` : '';
          const args = tc.argsSummary ? `(${tc.argsSummary})` : '';
          lines.push(`- [${mark}] ${tc.name}${args}${dur}`);
        }
        lines.push('', '</details>', '');
      }
      mdTurnIndex++;
    }
    lines.push('---');
    lines.push('');
  }

  return lines.join('\n');
}

export function formatChatAsJson(data: ExportData, options?: ExportFormatOptions): string {
  const includeReasoning = options?.includeReasoning ?? true;
  const includeToolCalls = options?.includeToolCalls ?? true;

  const messages = data.messages.map((msg) => {
    if (includeReasoning) {
      return msg;
    }
    const cleanMeta = { ...msg.metadata };
    delete cleanMeta.reasoning;
    delete cleanMeta.reasoning_content;
    return { ...msg, metadata: cleanMeta };
  });

  return JSON.stringify(
    {
      title: data.chat.title,
      source: data.chat.source,
      exportedAt: new Date().toISOString(),
      ...(data.agentInfo ? { agentInfo: data.agentInfo } : {}),
      messages,
      ...(data.usageSummary ? { usageSummary: data.usageSummary } : {}),
      ...(includeToolCalls && data.toolSummary ? { toolSummary: data.toolSummary } : {}),
      ...(includeToolCalls && data.toolCallDetails ? { toolCallDetails: data.toolCallDetails } : {}),
    },
    null,
    2,
  );
}

export function downloadFile(content: string, filename: string, mimeType: string): void {
  void triggerDownload(new Blob([content], { type: mimeType }), filename).catch((err) => {
    console.error('[chatExport] download failed:', err);
  });
}

export function downloadAsMarkdown(data: ExportData, options?: ExportFormatOptions): void {
  const content = formatChatAsMarkdown(data, options);
  downloadFile(content, buildFilename(data.chat.title, 'md'), 'text/markdown;charset=utf-8');
}

export function downloadAsJson(data: ExportData, options?: ExportFormatOptions): void {
  const content = formatChatAsJson(data, options);
  downloadFile(content, buildFilename(data.chat.title, 'json'), 'application/json;charset=utf-8');
}

/**
 * The language of an export page's wording: the app's own language, resolved the way the interface resolves it, not the
 * browser's, which differs for anyone who runs the app in another language. The page has wording in English and
 * Chinese only, so Traditional Chinese reads the Chinese set and every other language reads the English one.
 */
export function getExportLang(): 'en' | 'zh' {
  const locale = parseLocaleQueryParam(getClientLocale()) ?? defaultLocale;
  return locale === 'zh' || locale === 'zh-TW' ? 'zh' : 'en';
}

export async function downloadAsHtml(
  data: ExportData,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
  options?: ExportFormatOptions,
): Promise<void> {
  const { buildHtmlDocument } = await import('./chatExportHtml');
  const html = await buildHtmlDocument(data, theme, lang, options);
  downloadFile(html, buildFilename(data.chat.title, 'html'), 'text/html;charset=utf-8');
}

export async function copyAsMarkdown(data: ExportData, options?: ExportFormatOptions): Promise<void> {
  const content = formatChatAsMarkdown(data, options);
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

export async function printChat(
  data: ExportData,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
): Promise<void> {
  const { buildHtmlDocument } = await import('./chatExportHtml');
  await printHtmlDocument(await buildHtmlDocument(data, theme, lang));
}

// ---------------------------------------------------------------------------
// 单条消息导出
// ---------------------------------------------------------------------------

function buildSingleMessageExportData(message: Message, markdown: string, redacted = true): ExportData {
  const ts = message.createdAt?.toISOString?.() ?? new Date().toISOString();
  return {
    chat: { id: message.chatId, title: null, source: 'myrm', createdAt: ts },
    messages: [{ role: message.role, content: markdown, createdAt: ts, metadata: {} }],
    redacted,
  };
}

export function downloadMessageAsMarkdown(
  message: Message,
  includeReasoning: boolean,
  labels: MessageLabels,
  redact = true,
): void {
  const content = formatMessageMarkdown(message, includeReasoning, labels, redact);
  downloadFile(content, buildFilename(extractMessageTitle(message, redact), 'md'), 'text/markdown;charset=utf-8');
}

export async function downloadMessageAsHtml(
  message: Message,
  includeReasoning: boolean,
  labels: MessageLabels,
  theme: 'light' | 'dark' = 'light',
  lang: 'en' | 'zh' = 'en',
  redact = true,
): Promise<void> {
  const markdown = formatMessageMarkdown(message, includeReasoning, labels, redact, 'quote');
  const { buildHtmlDocument } = await import('./chatExportHtml');
  const html = await buildHtmlDocument(buildSingleMessageExportData(message, markdown, redact), theme, lang);
  downloadFile(html, buildFilename(extractMessageTitle(message, redact), 'html'), 'text/html;charset=utf-8');
}

export async function downloadMessageAsDocx(
  message: Message,
  includeReasoning: boolean,
  labels: MessageLabels,
  redact = true,
): Promise<void> {
  const markdown = formatMessageMarkdown(message, includeReasoning, labels, redact, 'quote');
  const { buildDocxBlob } = await import('./chatExportDocx');
  await triggerDownload(await buildDocxBlob(markdown), buildFilename(extractMessageTitle(message, redact), 'docx'));
}

export async function downloadMessageAsImage(element: HTMLElement, message: Message, redact = true): Promise<void> {
  const { default: html2canvas } = await import('html2canvas');
  const canvas = await html2canvas(element, {
    useCORS: true,
    backgroundColor: null,
    scale: 2,
    onclone: (clonedDoc: Document, clonedEl: HTMLElement) => {
      if (redact) {
        const walker = clonedDoc.createTreeWalker(clonedEl, NodeFilter.SHOW_TEXT);
        let node: Node | null;
        while ((node = walker.nextNode())) {
          if (node.nodeValue) {
            node.nodeValue = redactSensitiveClientText(node.nodeValue);
          }
        }
      }
    },
  });
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Failed to create image blob'))), 'image/png');
  });
  await triggerDownload(blob, buildFilename(extractMessageTitle(message, redact), 'png'));
}
