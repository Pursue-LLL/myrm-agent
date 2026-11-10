/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FlowPadMode } from '@/store/useFlowPadStore';
import { useFlowPadDraft } from '../useFlowPadDraft';

interface Session {
  isOpen: boolean;
  mode: FlowPadMode;
  sourcePid: number | null;
  initialText: string;
}

const OPEN_CHAT: Session = { isOpen: true, mode: 'chat', sourcePid: null, initialText: 'starter' };

function renderDraft(session: Session = OPEN_CHAT) {
  return renderHook((props: Session) => useFlowPadDraft(props), { initialProps: session });
}

/** Types into the draft and opens the screenshot full size, so a reset has something to clear. */
function editDraft(result: ReturnType<typeof renderDraft>['result']): void {
  act(() => {
    result.current.setText('typed words');
    result.current.setLightboxSrc('data:image/jpeg;base64,abc');
  });
}

describe('useFlowPadDraft', () => {
  it('starts from the initial text of the session with no screenshot open', () => {
    const { result } = renderDraft();

    expect(result.current.text).toBe('starter');
    expect(result.current.lightboxSrc).toBeNull();
  });

  it('keeps edits for as long as the session stays the same', () => {
    const { result, rerender } = renderDraft();
    editDraft(result);

    rerender({ ...OPEN_CHAT });

    expect(result.current.text).toBe('typed words');
    expect(result.current.lightboxSrc).toBe('data:image/jpeg;base64,abc');
  });

  it.each<[string, Partial<Session>]>([
    ['the initial text changes', { initialText: 'another capture' }],
    ['the mode changes', { mode: 'inline' }],
    ['the source window changes', { sourcePid: 42 }],
  ])('starts over when %s while the pad stays open', (_, change) => {
    const { result, rerender } = renderDraft();
    editDraft(result);

    rerender({ ...OPEN_CHAT, ...change });

    expect(result.current.text).toBe(change.initialText ?? 'starter');
    expect(result.current.lightboxSrc).toBeNull();
  });

  it('keeps what the pad shows while it closes and starts over when it opens again', () => {
    const { result, rerender } = renderDraft();
    editDraft(result);

    rerender({ isOpen: false, mode: 'chat', sourcePid: null, initialText: '' });
    expect(result.current.text).toBe('typed words');
    expect(result.current.lightboxSrc).toBe('data:image/jpeg;base64,abc');

    rerender({ ...OPEN_CHAT });
    expect(result.current.text).toBe('starter');
    expect(result.current.lightboxSrc).toBeNull();
  });
});
