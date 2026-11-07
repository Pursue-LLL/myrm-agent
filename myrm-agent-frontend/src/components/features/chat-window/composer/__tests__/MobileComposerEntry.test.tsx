import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ActionMode } from '@/store/chat/types';

const modeSwitch = vi.hoisted(() => vi.fn());
vi.mock('@/components/features/message-input-actions/SearchModeSelector', () => ({
  default: (props: { actionMode: ActionMode; setActionMode: (mode: ActionMode) => void }) => {
    modeSwitch(props);
    return <div data-testid="mode-switch" />;
  },
}));

import { MobileComposerEntry } from '../MobileComposerEntry';

function renderEntry() {
  const props = { actionMode: 'agent' as const, setActionMode: vi.fn(), onOpenSheet: vi.fn() };
  const view = render(<MobileComposerEntry {...props} />);
  return { ...props, ...view };
}

describe('MobileComposerEntry', () => {
  it('opens the action sheet from the plus button', () => {
    const { onOpenSheet } = renderEntry();

    fireEvent.click(screen.getByTestId('sendbox-mobile-plus-btn'));

    expect(onOpenSheet).toHaveBeenCalledTimes(1);
  });

  it('names the plus button for assistive technology', () => {
    renderEntry();

    expect(screen.getByRole('button', { name: 'input.expandToolbar' })).toBe(
      screen.getByTestId('sendbox-mobile-plus-btn'),
    );
  });

  it('hands the mode and its setter to the mode switch', () => {
    const { setActionMode } = renderEntry();

    expect(modeSwitch).toHaveBeenLastCalledWith({ actionMode: 'agent', setActionMode });
  });

  it('is shown only below the sm breakpoint, where the desktop controls are hidden', () => {
    const { container } = renderEntry();

    expect(Array.from(container.firstElementChild?.classList ?? [])).toEqual(
      expect.arrayContaining(['flex', 'sm:hidden']),
    );
  });

  // jsdom has no layout, so the 44x44 box itself is measured in a browser; this guards the classes that produce it:
  // the glyph box stays 28px, and the target grows up, down and left but not right, where the mode switch sits 6px away.
  it('keeps the 28px glyph while growing the touch target on every side except the mode switch', () => {
    renderEntry();

    expect(Array.from(screen.getByTestId('sendbox-mobile-plus-btn').classList)).toEqual(
      expect.arrayContaining([
        'size-7',
        'relative',
        'after:absolute',
        'after:-inset-y-2',
        'after:-left-3.5',
        'after:-right-0.5',
      ]),
    );
  });
});
