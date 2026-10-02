import { describe, it, expect } from 'vitest';
import { isImeComposing, IME_CONFIRM_ENTER_WINDOW_MS } from '../imeUtils';

type ImeEventLike = {
  key?: string;
  keyCode?: number;
  isComposing?: boolean;
  nativeEvent?: {
    isComposing?: boolean;
  };
};

describe('imeUtils - isImeComposing', () => {
  it('returns true when nativeEvent.isComposing is true', () => {
    const event: ImeEventLike = { nativeEvent: { isComposing: true } };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns true when event.isComposing is true', () => {
    const event: ImeEventLike = { isComposing: true };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns true when event.key is Process', () => {
    const event: ImeEventLike = { key: 'Process', isComposing: false };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns true when event.keyCode is 229', () => {
    const event: ImeEventLike = { keyCode: 229, isComposing: false };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('returns false for normal Enter press without IME composition', () => {
    const event: ImeEventLike = {
      key: 'Enter',
      keyCode: 13,
      isComposing: false,
      nativeEvent: { isComposing: false },
    };
    expect(isImeComposing(event as unknown as React.KeyboardEvent)).toBe(false);
  });

  it('swallows the Safari confirm Enter that arrives right after compositionend', () => {
    document.dispatchEvent(new Event('compositionend'));

    // Safari 顺序：compositionend -> keydown(Enter, isComposing=false, keyCode=13)
    const safariConfirmEnter: ImeEventLike = { key: 'Enter', keyCode: 13, isComposing: false };
    expect(isImeComposing(safariConfirmEnter as unknown as React.KeyboardEvent)).toBe(true);
  });

  it('releases the guard once the confirm window has elapsed', () => {
    document.dispatchEvent(new Event('compositionend'));

    const laterEnter: ImeEventLike = { key: 'Enter', keyCode: 13, isComposing: false };
    const afterWindow = Date.now() + IME_CONFIRM_ENTER_WINDOW_MS + 1;
    expect(isImeComposing(laterEnter as unknown as React.KeyboardEvent, afterWindow)).toBe(false);
  });

  it('never swallows non-Enter keys inside the confirm window', () => {
    document.dispatchEvent(new Event('compositionend'));

    const arrow: ImeEventLike = { key: 'ArrowUp', keyCode: 38, isComposing: false };
    expect(isImeComposing(arrow as unknown as React.KeyboardEvent)).toBe(false);
  });
});
