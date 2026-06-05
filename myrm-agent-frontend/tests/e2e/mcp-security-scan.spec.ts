import { test, expect } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

test.describe('MCP security scan', () => {
  test.skip(
    !process.env.PLAYWRIGHT_RUN_MCP_SCAN_E2E,
    'Set PLAYWRIGHT_RUN_MCP_SCAN_E2E=1 with backend on :8080',
  );

  test('POST /mcp/scan blocks hardcoded env secret', async ({ request }) => {
    const response = await request.post(`${apiBase}/api/v1/mcp/scan`, {
      data: {
        name: 'evil-import',
        type: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-github'],
        extraParams: {
          env: { GITHUB_TOKEN: 'ghp_1234567890abcdefghijklmnopqrstuvwxyz' },
        },
      },
    });
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as {
      success: boolean;
      data: { allowSave: boolean; maxSeverity: string | null; findings: { threatType: string }[] };
    };
    expect(body.success).toBe(true);
    expect(body.data.allowSave).toBe(false);
    expect(body.data.maxSeverity).toBe('critical');
    expect(body.data.findings.some((f) => f.threatType === 'hardcoded_secret')).toBe(true);
  });

  test('POST /mcp/scan allows clean SSE config', async ({ request }) => {
    const response = await request.post(`${apiBase}/api/v1/mcp/scan`, {
      data: {
        name: 'docs',
        type: 'sse',
        url: 'https://mcp.example.com/sse',
        description: 'Documentation MCP',
      },
    });
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as {
      success: boolean;
      data: { allowSave: boolean; findings: unknown[] };
    };
    expect(body.success).toBe(true);
    expect(body.data.allowSave).toBe(true);
    expect(body.data.findings).toHaveLength(0);
  });
});
