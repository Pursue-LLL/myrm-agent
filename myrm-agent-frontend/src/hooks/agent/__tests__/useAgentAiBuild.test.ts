import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useAgentAiBuild, type AiBuildTarget } from '../useAgentAiBuild';

const { toastMock, stableT } = vi.hoisted(() => ({ toastMock: vi.fn(), stableT: (key: string) => key }));

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));
vi.mock('@/lib/api', () => ({ getApiUrl: (path: string) => `/api/v1${path}` }));

const encoder = new TextEncoder();

/** A fetch response whose body streams the given SSE events. */
function sseResponse(...events: unknown[]) {
  const chunks = events.map((event) => encoder.encode(`data: ${JSON.stringify(event)}\n`));
  let next = 0;
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () =>
          next < chunks.length ? { done: false, value: chunks[next++] } : { done: true, value: undefined },
      }),
    },
  };
}

function makeTarget(): AiBuildTarget {
  return {
    setName: vi.fn(),
    setDescription: vi.fn(),
    handleConfigChange: vi.fn(),
    enabledSkills: [{ id: 'skill-a' }, { id: 'skill-b' }] as AiBuildTarget['enabledSkills'],
    enabledMcps: [{ name: 'github' }] as AiBuildTarget['enabledMcps'],
  };
}

describe('useAgentAiBuild', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  it('applies a streamed draft, keeping only what exists on this installation', async () => {
    fetchMock.mockResolvedValue(
      sseResponse(
        { type: 'thinking', data: 'ignored' },
        { type: 'content', data: '```json\n{"name":"Reporter","description":"Weekly reports",' },
        {
          type: 'content',
          data:
            '"system_prompt":"Write reports","skill_ids":["skill-a","ghost-skill"],' +
            '"mcp_ids":["github","ghost-mcp"],"builtin_tools":["search","teleport"]}\n```',
        },
      ),
    );
    const target = makeTarget();
    const { result } = renderHook(() => useAgentAiBuild(target));

    act(() => result.current.setAiIntent('a weekly report writer'));
    await act(() => result.current.handleAiBuild('a weekly report writer'));

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/user-agents/ai-build');
    expect(JSON.parse(init.body as string)).toMatchObject({ intent: 'a weekly report writer' });
    expect(target.setName).toHaveBeenCalledWith('Reporter');
    expect(target.setDescription).toHaveBeenCalledWith('Weekly reports');
    expect(target.handleConfigChange).toHaveBeenCalledWith({
      systemPrompt: 'Write reports',
      selectedSkillIds: ['skill-a'],
      selectedMcpNames: ['github'],
      enabledBuiltinTools: ['search'],
    });
    expect(result.current.aiIntent).toBe('');
    expect(result.current.aiGenerating).toBe(false);
    expect(toastMock).toHaveBeenCalledWith({ title: 'agent.aiBuilder.apply' });
  });

  it('does nothing for a blank intent', async () => {
    const { result } = renderHook(() => useAgentAiBuild(makeTarget()));

    await act(() => result.current.handleAiBuild('   '));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('tells the user to set up a model when the builder refuses for lack of one, and keeps the intent', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: { message: 'LLM provider is not configured', error_code: 'model_not_configured' } }),
    });
    const target = makeTarget();
    const { result } = renderHook(() => useAgentAiBuild(target));
    act(() => result.current.setAiIntent('a planner'));

    await act(() => result.current.handleAiBuild('a planner'));

    expect(toastMock).toHaveBeenCalledWith({
      title: 'agent.aiBuilder.error',
      description: 'agent.aiBuilder.noModel',
      variant: 'destructive',
    });
    expect(target.handleConfigChange).not.toHaveBeenCalled();
    expect(result.current.aiIntent).toBe('a planner');
    expect(result.current.aiGenerating).toBe(false);
  });

  it('keeps backend wording out of the toast for any other refusal', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, json: async () => ({ detail: 'upstream exploded' }) });
    const { result } = renderHook(() => useAgentAiBuild(makeTarget()));

    await act(() => result.current.handleAiBuild('a planner'));

    expect(toastMock).toHaveBeenCalledWith({
      title: 'agent.aiBuilder.error',
      description: undefined,
      variant: 'destructive',
    });
  });

  it('reports a draft that is not valid JSON instead of applying part of it', async () => {
    fetchMock.mockResolvedValue(sseResponse({ type: 'content', data: 'Sorry, I cannot build that.' }));
    const target = makeTarget();
    const { result } = renderHook(() => useAgentAiBuild(target));

    await act(() => result.current.handleAiBuild('a planner'));

    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'agent.aiBuilder.error', variant: 'destructive' }),
    );
    expect(target.setName).not.toHaveBeenCalled();
    expect(target.handleConfigChange).not.toHaveBeenCalled();
  });
});
