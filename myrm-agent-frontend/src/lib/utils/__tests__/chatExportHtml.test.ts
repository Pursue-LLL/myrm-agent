/** @vitest-environment jsdom */
import { describe, it, expect } from 'vitest';
import { buildHtmlDocument } from '../chatExportHtml';
import type { ExportData } from '../chatExport';

function createMockExportData(overrides: Partial<ExportData> = {}): ExportData {
  return {
    chat: { id: 'chat-test-1', title: 'Export HTML Test', source: 'myrm', createdAt: '2026-10-01T10:00:00Z' },
    messages: [
      {
        role: 'user',
        content: 'Please optimize this SQL query',
        createdAt: '2026-10-01T10:01:00Z',
        metadata: {},
      },
      {
        role: 'assistant',
        content: '```sql\nSELECT * FROM orders WHERE status = "active";\n```',
        createdAt: '2026-10-01T10:02:00Z',
        metadata: {
          reasoning_content: 'Analyzing table structure and indexed columns',
          token_usage: { prompt_tokens: 50, completion_tokens: 30, total_tokens: 80 },
        },
      },
    ],
    redacted: true,
    toolSummary: {
      totalToolCalls: 2,
      totalDurationMs: 1250,
      toolsUsed: [{ name: 'db_explain', count: 2, totalMs: 1250 }],
    },
    toolCallDetails: [
      { turnIndex: 0, name: 'db_explain', durationMs: 1250, argsSummary: 'table: orders', success: true },
    ],
    agentInfo: {
      name: 'SQL Specialist',
      model: 'claude-3-7-sonnet',
      description: 'Database performance optimizer',
    },
    ...overrides,
  };
}

describe('chatExportHtml - buildHtmlDocument', () => {
  it('renders a self-contained HTML document with dark and light themes', async () => {
    const data = createMockExportData();
    const html = await buildHtmlDocument(data, 'dark', 'en');

    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<html lang="en" data-theme="dark">');
    expect(html).toContain('Export HTML Test - Myrm');
    expect(html).toContain('SQL Specialist');
    expect(html).toContain('claude-3-7-sonnet');
    expect(html).toContain('db_explain');
    expect(html).toContain('Analyzing table structure');
  });

  it('strictly adheres to zero native emojis and renders text badges', async () => {
    const data = createMockExportData({ redacted: true });
    const htmlZh = await buildHtmlDocument(data, 'dark', 'zh');
    const htmlEn = await buildHtmlDocument(data, 'light', 'en');

    // Verify presence of text security badges
    expect(htmlZh).toContain('[Security] 本会话已启用敏感凭据自动脱敏安全保护');
    expect(htmlEn).toContain('[Security] Sensitive secrets and credentials have been automatically redacted.');

    // Verify theme toggle text does not have emojis
    expect(htmlZh).toContain('id="theme-toggle">Light</button>');
    expect(htmlEn).toContain('id="theme-toggle">Dark</button>');

    // Strict regex check for any emoji unicode blocks across entire output
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    expect(emojiRegex.test(htmlZh)).toBe(false);
    expect(emojiRegex.test(htmlEn)).toBe(false);
  });

  it('renders localized labels accurately for both zh and en', async () => {
    const data = createMockExportData();
    const htmlZh = await buildHtmlDocument(data, 'light', 'zh');
    const htmlEn = await buildHtmlDocument(data, 'light', 'en');

    expect(htmlZh).toContain('工具调用');
    expect(htmlZh).toContain('深度思考');
    expect(htmlZh).toContain('导出自 Myrm');

    expect(htmlEn).toContain('Tool Activity');
    expect(htmlEn).toContain('Thinking');
    expect(htmlEn).toContain('Exported from Myrm');
  });

  it('renders code-header with copy button and interactive clipboard script', async () => {
    const data = createMockExportData();
    const html = await buildHtmlDocument(data, 'dark', 'en');

    // Code block container and header
    expect(html).toContain('class="code-block"');
    expect(html).toContain('class="code-header"');
    expect(html).toContain('<span class="code-lang">sql</span>');
    expect(html).toContain('<button class="copy-code-btn" type="button" aria-label="Copy code">Copy</button>');

    // Interactive script includes copy delegation and fallback
    expect(html).toContain('.copy-code-btn');
    expect(html).toContain('showCopied');
    expect(html).toContain('navigator.clipboard.writeText');
  });
});
