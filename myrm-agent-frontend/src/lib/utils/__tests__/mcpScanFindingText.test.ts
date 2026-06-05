import { describe, expect, it, vi } from 'vitest';

import type { MCPScanFinding } from '@/store/config/types';
import {
  formatMcpGateBlockedMessage,
  getMcpFindingDescription,
  parseMcpFindingsFromApiErrorDetails,
} from '@/lib/utils/mcpScanFindingText';

describe('mcpScanFindingText', () => {
  const t = vi.fn((key: string) => {
    const map: Record<string, string> = {
      'mcpThreat.prompt_injection': '检测到提示词注入风险',
      'mcpThreat.name_injection': '工具名称含注入特征',
      'settings.mcp.verifyFailed': 'MCP 验证失败',
    };
    return map[key] ?? key;
  });

  it('maps threat_type to localized description', () => {
    const finding: MCPScanFinding = {
      threatType: 'prompt_injection',
      severity: 'high',
      description: 'English fallback',
      field: 'description',
    };
    expect(getMcpFindingDescription(finding, t)).toBe('检测到提示词注入风险');
  });

  it('parses structured findings from API error details', () => {
    const payload = JSON.stringify({
      threatType: 'name_injection',
      severity: 'high',
      description: 'Tool name contains injection-like content',
      recommendation: 'Rename the tool',
    });
    const findings = parseMcpFindingsFromApiErrorDetails([
      { field: 'tool.name', issue: payload },
    ]);
    expect(findings).toHaveLength(1);
    expect(findings[0]?.threatType).toBe('name_injection');
  });

  it('prefers verify findings in gate blocked message', () => {
    const message = formatMcpGateBlockedMessage(
      {
        verifyError: 'raw english error',
        verifyFindings: [
          {
            threatType: 'name_injection',
            severity: 'high',
            description: 'English fallback',
            field: 'tool.name',
          },
        ],
        fallback: 'fallback',
      },
      t,
    );
    expect(message).toContain('工具名称含注入特征');
    expect(message).toContain('tool.name');
  });
});
