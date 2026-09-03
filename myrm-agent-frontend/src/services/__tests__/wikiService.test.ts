import { describe, expect, it } from 'vitest';

import { buildWikiApiPath, buildWikiQueryRequestBody } from '@/services/wikiService';

describe('wikiService query payload', () => {
  it('defaults retrieval mode to auto', () => {
    expect(buildWikiQueryRequestBody('What is revenue growth?')).toEqual({
      question: 'What is revenue growth?',
      mode: 'auto',
    });
  });

  it('includes raw_claim mode when selected', () => {
    expect(buildWikiQueryRequestBody('Annual revenue claim', 'raw_claim')).toEqual({
      question: 'Annual revenue claim',
      mode: 'raw_claim',
    });
  });
});

describe('buildWikiApiPath', () => {
  it('returns the base path when agent scope is empty', () => {
    expect(buildWikiApiPath('/wiki/pending')).toBe('/wiki/pending');
    expect(buildWikiApiPath('/wiki/pending', '   ')).toBe('/wiki/pending');
  });

  it('appends agent_id query parameter for scoped requests', () => {
    expect(buildWikiApiPath('/wiki/pending', 'agent-a')).toBe('/wiki/pending?agent_id=agent-a');
    expect(buildWikiApiPath('/wiki/concepts?limit=10', 'agent/b')).toBe('/wiki/concepts?limit=10&agent_id=agent%2Fb');
  });

  it('formats import urls path correctly', () => {
    expect(buildWikiApiPath('/wiki/import/urls', null)).toBe('/wiki/import/urls');
    expect(buildWikiApiPath('/wiki/import/urls', 'agent-kb')).toBe('/wiki/import/urls?agent_id=agent-kb');
  });
});
