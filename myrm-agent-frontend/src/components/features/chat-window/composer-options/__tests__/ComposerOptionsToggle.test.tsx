import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';

import { ComposerOptionsToggle } from '../ComposerOptionsToggle';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function renderToggle(expanded: boolean, onToggle = vi.fn()) {
  render(<ComposerOptionsToggle expanded={expanded} onToggle={onToggle} controlsId="options-region" />);
  return { onToggle, button: screen.getByTestId('composer-options-toggle') };
}

describe('composer options toggle', () => {
  beforeEach(() => {
    // The tooltip arrow measures itself once the tooltip opens on focus.
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
    useChatStore.setState({ actionMode: 'agent', searchDepth: 'normal', isWorkflowMode: false, incognitoMode: false });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('offers to open the region it controls while the region is closed', () => {
    const { button } = renderToggle(false);

    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(button).toHaveAttribute('aria-controls', 'options-region');
    expect(button).toHaveAccessibleName('展开工具栏');
    expect(screen.queryByTestId('composer-options-active-dot')).toBeNull();
  });

  it('offers to close the region while it is open', () => {
    const { button } = renderToggle(true);

    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAccessibleName('收起工具栏');
  });

  it('says which modes are on, in the accessible name and with a dot, so a closed region hides nothing', () => {
    useChatStore.setState({ isWorkflowMode: true });
    const { button } = renderToggle(false);

    expect(button).toHaveAccessibleName('展开工具栏 · 已启用：编排模式 (PTC)');
    expect(screen.getByTestId('composer-options-active-dot')).toHaveAttribute('aria-hidden', 'true');
  });

  it('picks up a mode that is switched on later', () => {
    const { button } = renderToggle(false);
    expect(screen.queryByTestId('composer-options-active-dot')).toBeNull();

    act(() => useChatStore.setState({ incognitoMode: true }));

    expect(button).toHaveAccessibleName('展开工具栏 · 已启用：无痕模式');
    expect(screen.getByTestId('composer-options-active-dot')).toBeInTheDocument();
  });

  it('reports a click once', async () => {
    const user = userEvent.setup();
    const { button, onToggle } = renderToggle(false);

    await user.click(button);

    expect(onToggle).toHaveBeenCalledTimes(1);
  });
});
