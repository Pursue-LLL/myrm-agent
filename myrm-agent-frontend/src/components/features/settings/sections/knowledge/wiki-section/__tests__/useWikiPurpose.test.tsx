/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { apiRequest, resetKit, toast } from './wikiSectionTestKit';
import { useWikiPurpose } from '../useWikiPurpose';

const PURPOSE_PATH = '/wiki/purpose';

let consoleError: ReturnType<typeof vi.spyOn>;

async function setup(scope: string | null = null) {
  const rendered = renderHook(({ scopeId }) => useWikiPurpose(scopeId), { initialProps: { scopeId: scope } });
  await settle();
  return rendered;
}

const edit = (result: { current: ReturnType<typeof useWikiPurpose> }, draft: string) =>
  act(() => result.current.setPurposeDraft(draft));

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  consoleError.mockRestore();
});

describe('useWikiPurpose: loading', () => {
  it('starts empty, shows the load, then holds the saved purpose in both the value and the draft', async () => {
    const pending = deferred<{ purpose: string }>();
    apiRequest.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useWikiPurpose(null));
    expect(result.current.isLoadingPurpose).toBe(true);
    expect(result.current.purpose).toBe('');
    expect(result.current.purposeDraft).toBe('');

    pending.resolve({ purpose: 'Track the product roadmap' });
    await settle();
    expect(result.current.isLoadingPurpose).toBe(false);
    expect(result.current.purpose).toBe('Track the product roadmap');
    expect(result.current.purposeDraft).toBe('Track the product roadmap');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(PURPOSE_PATH);
  });

  it('asks for the purpose of the agent scope', async () => {
    await setup('a1');
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(`${PURPOSE_PATH}?agent_id=a1`);
  });

  it('loads the purpose of the new scope when the scope changes, replacing an unsaved draft', async () => {
    apiRequest.mockResolvedValueOnce({ purpose: 'first' }).mockResolvedValueOnce({ purpose: 'second' });
    const { result, rerender } = await setup('a1');
    edit(result, 'half-typed');
    rerender({ scopeId: 'a2' });
    await settle();
    expect(apiRequest).toHaveBeenLastCalledWith(`${PURPOSE_PATH}?agent_id=a2`);
    expect(result.current.purpose).toBe('second');
    expect(result.current.purposeDraft).toBe('second');
  });

  it('does not reload when the scope stays the same', async () => {
    const { rerender } = await setup('a1');
    rerender({ scopeId: 'a1' });
    await settle();
    expect(apiRequest).toHaveBeenCalledOnce();
  });

  it('stays empty and quiet for the user when the load fails, and logs the cause', async () => {
    const failure = new Error('offline');
    apiRequest.mockRejectedValue(failure);
    const { result } = await setup();
    expect(result.current.purpose).toBe('');
    expect(result.current.isLoadingPurpose).toBe(false);
    expect(toast.error).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Failed to load purpose:', failure);
  });
});

describe('useWikiPurpose: editing and saving', () => {
  it('keeps the draft apart from the saved purpose while the user types', async () => {
    const { result } = await setup();
    edit(result, 'a new purpose');
    expect(result.current.purposeDraft).toBe('a new purpose');
    expect(result.current.purpose).toBe('saved purpose');
  });

  it('saves the draft with a PUT, adopts it as the purpose and confirms', async () => {
    const { result } = await setup('a1');
    edit(result, 'a new purpose');
    apiRequest.mockClear();
    const pending = deferred<object>();
    apiRequest.mockReturnValue(pending.promise);

    let saving: Promise<void> = Promise.resolve();
    act(() => {
      saving = result.current.handleSavePurpose();
    });
    expect(result.current.isSavingPurpose).toBe(true);
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith(`${PURPOSE_PATH}?agent_id=a1`, {
      method: 'PUT',
      body: JSON.stringify({ purpose: 'a new purpose' }),
    });
    expect(result.current.purpose).toBe('saved purpose');

    pending.resolve({});
    await act(() => saving);
    expect(result.current.isSavingPurpose).toBe(false);
    expect(result.current.purpose).toBe('a new purpose');
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('success.purposeSaved');
  });

  it('keeps the saved purpose and the draft and reports a failed save', async () => {
    const { result } = await setup();
    edit(result, 'a new purpose');
    const failure = new Error('no write access');
    apiRequest.mockRejectedValue(failure);
    await act(() => result.current.handleSavePurpose());
    expect(result.current.isSavingPurpose).toBe(false);
    expect(result.current.purpose).toBe('saved purpose');
    expect(result.current.purposeDraft).toBe('a new purpose');
    expect(toast.error).toHaveBeenCalledExactlyOnceWith('errors.purposeSaveFailed');
    expect(toast.success).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledWith('Failed to save purpose:', failure);
  });
});
