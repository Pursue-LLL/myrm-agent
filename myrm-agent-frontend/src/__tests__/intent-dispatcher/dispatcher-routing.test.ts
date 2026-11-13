import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { IntentDispatcher } from '@/lib/intent-dispatcher';

const mocks = vi.hoisted(() => ({ toastError: vi.fn() }));

vi.mock('sonner', () => ({ toast: { error: mocks.toastError, success: vi.fn() } }));

const messages = {
  invalidLink: 'invalid',
  oauthSuccess: 'ok',
  oauthFailed: 'failed',
  cloudProfileName: 'Cloud box',
};

describe('dispatcher navigation intents', () => {
  let pushed: string[];
  let openFlowPad: ReturnType<typeof vi.fn<(text: string) => void>>;
  let dispatcher: IntentDispatcher;

  beforeEach(() => {
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    pushed = [];
    openFlowPad = vi.fn<(text: string) => void>();
    const router = { push: (url: string) => pushed.push(url) } as unknown as AppRouterInstance;
    dispatcher = new IntentDispatcher(router, openFlowPad, messages);
    mocks.toastError.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens a chat on its own route', async () => {
    expect(await dispatcher.dispatch('myrmagent://chat/c-12345')).toBe(true);
    expect(pushed).toEqual(['/chat/c-12345']);
  });

  it('opens an agent in the Settings agent editor', async () => {
    expect(await dispatcher.dispatch('myrmagent://agent/office-doc')).toBe(true);
    expect(pushed).toEqual(['/settings/agents?agentId=office-doc']);
  });

  it('opens an agent from a web deep link the same way', async () => {
    expect(await dispatcher.dispatch('https://app.myrmagent.com/intent/agent/builtin-general')).toBe(true);
    expect(pushed).toEqual(['/settings/agents?agentId=builtin-general']);
  });

  it('keeps an agent id from adding query parameters of its own', async () => {
    expect(await dispatcher.dispatch('myrmagent://agent/a&new=true')).toBe(true);
    expect(pushed).toEqual(['/settings/agents?agentId=a%26new%3Dtrue']);
  });

  it('hands a quick-ask query to the flow pad without navigating', async () => {
    expect(await dispatcher.dispatch('myrmagent://ask?text=hello%20world')).toBe(true);
    expect(openFlowPad).toHaveBeenCalledWith('hello world');
    expect(pushed).toEqual([]);
  });

  it('opens the skill installer with the encoded source url', async () => {
    expect(await dispatcher.dispatch('myrmagent://install-skill?url=https%3A%2F%2Fexample.com%2Fskill.json')).toBe(
      true,
    );
    expect(pushed).toEqual(['/settings/skills?action=install&url=https%3A%2F%2Fexample.com%2Fskill.json']);
  });

  it('rejects an unknown link with a toast and no navigation', async () => {
    expect(await dispatcher.dispatch('myrmagent://hack/123')).toBe(false);
    expect(mocks.toastError).toHaveBeenCalledWith('invalid');
    expect(pushed).toEqual([]);
  });
});
