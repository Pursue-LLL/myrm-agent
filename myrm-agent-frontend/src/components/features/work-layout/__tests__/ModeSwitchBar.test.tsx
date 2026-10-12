/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ModeSwitchBar } from '../ModeSwitchBar';
import { useWorkLayoutStore } from '@/store/useWorkLayoutStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ModeSwitchBar component', () => {
  beforeEach(() => {
    useWorkLayoutStore.setState({
      viewMode: 'chat',
    });
  });

  it('renders chat and work mode buttons with chat selected by default', () => {
    render(<ModeSwitchBar />);

    const chatBtn = screen.getByRole('button', { name: /modeChat/i });
    const workBtn = screen.getByRole('button', { name: /modeWork/i });

    expect(chatBtn).toBeDefined();
    expect(workBtn).toBeDefined();
    expect(chatBtn.getAttribute('aria-pressed')).toBe('true');
    expect(workBtn.getAttribute('aria-pressed')).toBe('false');
  });

  it('switches viewMode to work on clicking work button', () => {
    render(<ModeSwitchBar />);

    const workBtn = screen.getByRole('button', { name: /modeWork/i });
    fireEvent.click(workBtn);

    expect(useWorkLayoutStore.getState().viewMode).toBe('work');
    expect(workBtn.getAttribute('aria-pressed')).toBe('true');
  });

  it('toggles mode on pressing Cmd+Shift+M / Ctrl+Shift+M', () => {
    render(<ModeSwitchBar />);

    expect(useWorkLayoutStore.getState().viewMode).toBe('chat');

    fireEvent.keyDown(window, { key: 'M', metaKey: true, shiftKey: true });
    expect(useWorkLayoutStore.getState().viewMode).toBe('work');

    fireEvent.keyDown(window, { key: 'm', ctrlKey: true, shiftKey: true });
    expect(useWorkLayoutStore.getState().viewMode).toBe('chat');
  });
});
