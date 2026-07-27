import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import { wikiService } from '@/services/wikiService';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('wikiService.queryWiki', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    wikiService.setAgentScope(undefined);
    apiRequestMock.mockResolvedValue({
      answer: 'ok',
      related_articles: [],
      source_snippets: [],
    });
  });

  it('posts wiki query without agent scope by default', async () => {
    await wikiService.queryWiki('where is my policy');

    expect(apiRequestMock).toHaveBeenCalledWith('/wiki/query', {
      method: 'POST',
      body: JSON.stringify({ question: 'where is my policy' }),
    });
  });

  it('posts wiki query with scoped agent id when scope is set', async () => {
    wikiService.setAgentScope('agent-123');

    await wikiService.queryWiki('where is my policy');

    expect(apiRequestMock).toHaveBeenCalledWith('/wiki/query?agent_id=agent-123', {
      method: 'POST',
      body: JSON.stringify({ question: 'where is my policy' }),
    });
  });

  it('trims scoped agent id before building query URL', async () => {
    wikiService.setAgentScope('  agent-456  ');

    await wikiService.queryWiki('where is my policy');

    expect(apiRequestMock).toHaveBeenCalledWith('/wiki/query?agent_id=agent-456', {
      method: 'POST',
      body: JSON.stringify({ question: 'where is my policy' }),
    });
  });
});
