/**
 * [INPUT] @/services/statistics::SessionAnalytics (POS: 会话分析 DTO)
 * [OUTPUT] buildAuditMarkdown / buildAuditCsv: 审计账本的 Markdown 与 CSV 文本; copyTextToClipboard / downloadCsvFile: 写入剪贴板与触发下载
 * [POS] SessionAnalyticsDialog 的导出动作，纯函数加浏览器 API 调用，不持有状态。
 */

import type { SessionAnalytics } from '@/services/statistics';

export function buildAuditMarkdown(data: SessionAnalytics): string {
  const durSec = Math.round(data.duration_ms / 1000);
  const durStr = durSec >= 60 ? `${Math.floor(durSec / 60)}m ${durSec % 60}s` : `${durSec}s`;

  const llmRows =
    data.llm_breakdown && data.llm_breakdown.length > 0
      ? data.llm_breakdown
          .map(
            (item) =>
              `| ${item.model_name} | ${item.call_count} | ${item.total_duration_ms} ms | ${item.call_count > 0 ? Math.round(item.total_duration_ms / item.call_count) : 0} ms |`,
          )
          .join('\n')
      : '| N/A | 0 | 0 ms | 0 ms |';

  const toolRows =
    data.tool_breakdown && data.tool_breakdown.length > 0
      ? data.tool_breakdown
          .map(
            (item) =>
              `| ${item.tool_name} | ${item.call_count} | ${item.total_duration_ms} ms | ${item.call_count > 0 ? Math.round(item.total_duration_ms / item.call_count) : 0} ms |`,
          )
          .join('\n')
      : '| N/A | 0 | 0 ms | 0 ms |';

  const markdown = `# 📋 Myrm Task Audit Ledger

- **Session Title**: ${data.title || 'Untitled Session'}
- **Session ID**: \`${data.session_id}\`
- **Action Mode**: ${data.action_mode}
- **Timestamp**: ${data.created_at ? new Date(data.created_at).toLocaleString() : 'N/A'}
- **Total Duration**: ${durStr}
- **Total Messages**: ${data.message_count} (User: ${data.user_messages}, Assistant: ${data.assistant_messages})
- **Total Tokens**: ${data.totalTokens.toLocaleString()} (Input: ${data.inputTokens.toLocaleString()}, Output: ${data.outputTokens.toLocaleString()}, Cached: ${data.cachedTokens.toLocaleString()})
- **Prompt Cache Hit Ratio**: ${(data.cacheHitRate * 100).toFixed(1)}%
- **Estimated Cost**: $${data.costUsd.toFixed(4)} USD

### 🤖 LLM Breakdown
| Model | Calls | Total Duration | Avg Latency |
| :--- | :--- | :--- | :--- |
${llmRows}

### 🛠️ Tool & Sandbox Breakdown
| Tool Name | Calls | Total Duration | Avg Latency |
| :--- | :--- | :--- | :--- |
${toolRows}
`;
  return markdown;
}

/** Resolves true once the text is on the clipboard (async API first, then the execCommand fallback). */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (
      typeof navigator !== 'undefined' &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === 'function'
    ) {
      await navigator.clipboard.writeText(text);
      return true;
    }
    throw new Error('Clipboard API unavailable in this context');
  } catch {
    // Insecure context (HTTP LAN) or restricted iframe fallback
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      textarea.style.top = '-9999px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textarea);
      return successful;
    } catch {
      // Silent fallback
      return false;
    }
  }
}

export function buildAuditCsv(data: SessionAnalytics): string {
  const durSec = Math.round(data.duration_ms / 1000);
  const escapeCsv = (val: string | number) => `"${String(val).replace(/"/g, '""')}"`;

  const lines: string[] = [
    '\uFEFFSection,Metric,Value',
    `Session,Title,${escapeCsv(data.title || 'Untitled Session')}`,
    `Session,SessionId,${escapeCsv(data.session_id)}`,
    `Session,Mode,${escapeCsv(data.action_mode)}`,
    `Session,CreatedAt,${escapeCsv(data.created_at || '')}`,
    `Session,DurationSeconds,${durSec}`,
    `Session,TotalMessages,${data.message_count}`,
    `Session,UserMessages,${data.user_messages}`,
    `Session,AssistantMessages,${data.assistant_messages}`,
    `Economics,TotalTokens,${data.totalTokens}`,
    `Economics,InputTokens,${data.inputTokens}`,
    `Economics,OutputTokens,${data.outputTokens}`,
    `Economics,CachedTokens,${data.cachedTokens}`,
    `Economics,CacheHitRatio,${(data.cacheHitRate * 100).toFixed(2)}%`,
    `Economics,CostUSD,${data.costUsd.toFixed(4)}`,
    '',
    'Type,Name,Calls,TotalDurationMs',
  ];

  if (data.llm_breakdown) {
    data.llm_breakdown.forEach((item) => {
      lines.push(`LLM,${escapeCsv(item.model_name)},${item.call_count},${item.total_duration_ms}`);
    });
  }

  if (data.tool_breakdown) {
    data.tool_breakdown.forEach((item) => {
      lines.push(`Tool,${escapeCsv(item.tool_name)},${item.call_count},${item.total_duration_ms}`);
    });
  }
  return lines.join('\n');
}

export function downloadCsvFile(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
