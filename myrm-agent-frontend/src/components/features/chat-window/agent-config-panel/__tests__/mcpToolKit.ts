import { vi } from 'vitest';
import type { FetchMCPToolsResult, MCPToolDetail } from '@/services/llm-config';
import type { MCPServiceConfig } from '@/store/config/types';

/**
 * Mocks and builders shared by the MCP tool selector tests. It never imports the component, so the mock
 * factories that load it cannot end up in a loading cycle with the module under test.
 */
const hoisted = vi.hoisted(() => ({
  fetchMCPTools: vi.fn<(config: MCPServiceConfig) => Promise<FetchMCPToolsResult>>(),
  t: (key: string, params?: Record<string, unknown>) => (params ? `${key} ${JSON.stringify(params)}` : key),
}));
export { hoisted as kit };

export const llmConfigMock = () => ({ fetchMCPTools: hoisted.fetchMCPTools });

export const nextIntlMock = () => ({ useTranslations: () => hoisted.t });

/** A tool that changes nothing and can be repeated: the safe kind. */
export const readOnlyTool = (name: string, overrides: Partial<MCPToolDetail> = {}): MCPToolDetail => ({
  name,
  description: `${name} description`,
  readOnlyHint: true,
  destructiveHint: false,
  idempotentHint: true,
  openWorldHint: false,
  ...overrides,
});

export const writableTool = (name: string): MCPToolDetail =>
  readOnlyTool(name, { readOnlyHint: false, idempotentHint: false });

export const destructiveTool = (name: string): MCPToolDetail =>
  readOnlyTool(name, { readOnlyHint: false, idempotentHint: false, destructiveHint: true });

export const serverConfig = (name = 'docs'): MCPServiceConfig => ({
  name,
  type: 'sse',
  url: `https://${name}.example.test/sse`,
  description: '',
  enabled: true,
});

export const toolsRead = (...tools: MCPToolDetail[]): FetchMCPToolsResult => ({ tools, error: false });

export const failedRead: FetchMCPToolsResult = { tools: [], error: true };
