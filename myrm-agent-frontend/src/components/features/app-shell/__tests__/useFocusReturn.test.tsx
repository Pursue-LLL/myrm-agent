/** @vitest-environment jsdom */
import { renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useFocusReturn } from '../useFocusReturn';

interface Props {
  open: boolean;
  enabled: boolean;
}

/** Opens the modal while `opener` has focus, then lets it close and returns what Radix would be told. */
function closeAfterOpeningFrom(opener: HTMLElement | null, enabled = true) {
  opener?.focus();
  const { result, rerender } = renderHook(({ open, enabled }: Props) => useFocusReturn(open, enabled), {
    initialProps: { open: false, enabled },
  });
  rerender({ open: true, enabled });
  // Focus moves into the modal, as Radix does.
  const inside = document.body.appendChild(document.createElement('button'));
  inside.focus();
  const event = new Event('focus', { cancelable: true });
  result.current(event);
  return { event, inside };
}

describe('useFocusReturn', () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it('puts focus back on the element that was focused when the modal opened', () => {
    const opener = document.body.appendChild(document.createElement('button'));

    const { event } = closeAfterOpeningFrom(opener);

    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(opener);
  });

  it('puts focus back on the button that opened the menu when the action came from one of its items', () => {
    const trigger = document.body.appendChild(document.createElement('button'));
    trigger.id = 'menu-trigger';
    const menu = document.body.appendChild(document.createElement('div'));
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-labelledby', 'menu-trigger');
    const item = menu.appendChild(document.createElement('div'));
    item.setAttribute('role', 'menuitem');
    item.tabIndex = -1;

    const { event } = closeAfterOpeningFrom(item);

    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(trigger);
  });

  it('leaves focus to Radix when nothing had focus', () => {
    const { event, inside } = closeAfterOpeningFrom(null);

    expect(event.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(inside);
  });

  it('leaves focus to Radix when the modal has a trigger of its own', () => {
    const opener = document.body.appendChild(document.createElement('button'));

    const { event, inside } = closeAfterOpeningFrom(opener, false);

    expect(event.defaultPrevented).toBe(false);
    expect(document.activeElement).toBe(inside);
  });

  it('does not chase an element that has left the page', () => {
    const opener = document.body.appendChild(document.createElement('button'));
    opener.focus();
    const { result, rerender } = renderHook(({ open, enabled }: Props) => useFocusReturn(open, enabled), {
      initialProps: { open: false, enabled: true },
    });
    rerender({ open: true, enabled: true });
    opener.remove();
    const event = new Event('focus', { cancelable: true });

    result.current(event);

    expect(event.defaultPrevented).toBe(false);
  });
});
