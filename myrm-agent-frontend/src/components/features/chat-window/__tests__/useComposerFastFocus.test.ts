/** @vitest-environment jsdom */
import { renderHook, act } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import {
  focusComposer,
  useComposerFastFocus,
} from '../useComposerFastFocus';

describe('useComposerFastFocus & focusComposer', () => {
  let mockContainer: HTMLDivElement;
  let mockInput: HTMLTextAreaElement;

  beforeEach(() => {
    mockContainer = document.createElement('div');
    mockContainer.setAttribute('data-chat-composer', 'true');

    mockInput = document.createElement('textarea');
    mockInput.setAttribute('data-chat-input', 'true');
    mockInput.value = 'Hello Assistant';

    mockContainer.appendChild(mockInput);
    document.body.appendChild(mockContainer);
  });

  afterEach(() => {
    if (mockContainer.parentElement) {
      mockContainer.parentElement.removeChild(mockContainer);
    }
    vi.restoreAllMocks();
  });

  it('successfully focuses input and sets cursor to end when input exists', () => {
    const focusSpy = vi.spyOn(mockInput, 'focus');
    const setSelectionRangeSpy = vi.spyOn(mockInput, 'setSelectionRange');

    const result = focusComposer();
    expect(result).toBe(true);
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(setSelectionRangeSpy).toHaveBeenCalledWith(15, 15);
  });

  it('returns false gracefully when data-chat-input does not exist in DOM', () => {
    mockContainer.removeChild(mockInput);
    const result = focusComposer();
    expect(result).toBe(false);
  });

  it('triggers onFocus callback and focuses input on Mod+K shortcut', () => {
    const onFocusMock = vi.fn();
    renderHook(() => useComposerFastFocus({ enabled: true, onFocus: onFocusMock }));

    const focusSpy = vi.spyOn(mockInput, 'focus');

    // Fire Cmd+K
    const event = new KeyboardEvent('keydown', {
      key: 'k',
      metaKey: true,
      cancelable: true,
    });
    window.dispatchEvent(event);

    expect(focusSpy).toHaveBeenCalled();
    expect(onFocusMock).toHaveBeenCalledTimes(1);
  });

  it('triggers onFocus on Mod+Shift+C shortcut', () => {
    const onFocusMock = vi.fn();
    renderHook(() => useComposerFastFocus({ enabled: true, onFocus: onFocusMock }));

    const focusSpy = vi.spyOn(mockInput, 'focus');

    // Fire Ctrl+Shift+C
    const event = new KeyboardEvent('keydown', {
      key: 'c',
      ctrlKey: true,
      shiftKey: true,
      cancelable: true,
    });
    window.dispatchEvent(event);

    expect(focusSpy).toHaveBeenCalled();
    expect(onFocusMock).toHaveBeenCalledTimes(1);
  });

  it('responds to global myrm:focus-composer custom event', () => {
    const onFocusMock = vi.fn();
    renderHook(() => useComposerFastFocus({ enabled: true, onFocus: onFocusMock }));

    act(() => {
      window.dispatchEvent(new CustomEvent('myrm:focus-composer'));
    });

    expect(onFocusMock).toHaveBeenCalledTimes(1);
  });

  it('does not intercept shortcut when enabled is false', () => {
    const onFocusMock = vi.fn();
    renderHook(() => useComposerFastFocus({ enabled: false, onFocus: onFocusMock }));

    const event = new KeyboardEvent('keydown', {
      key: 'k',
      metaKey: true,
      cancelable: true,
    });
    window.dispatchEvent(event);

    expect(onFocusMock).not.toHaveBeenCalled();
  });
});
