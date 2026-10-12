/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DualModeContainer } from '../DualModeContainer';
import { useWorkLayoutStore } from '@/store/useWorkLayoutStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('DualModeContainer component', () => {
  beforeEach(() => {
    useWorkLayoutStore.setState({
      viewMode: 'chat',
      computeTier: 'turbo',
      isSidebarCollapsed: false,
    });
  });

  it('renders chat mode by default with header controls and children', () => {
    render(
      <DualModeContainer>
        <div data-testid="chat-viewport">Chat Viewport Body</div>
      </DualModeContainer>,
    );

    const container = screen.getByTestId('dual-mode-container');
    expect(container.getAttribute('data-mode')).toBe('chat');
    expect(container.getAttribute('data-tier')).toBe('turbo');

    expect(screen.getByRole('banner', { name: 'Mode & Compute Tier Controller' })).toBeDefined();
    expect(screen.getByTestId('chat-viewport')).toBeDefined();

    // In chat mode, work asset sidebar is not displayed
    expect(screen.queryByLabelText('Work Assets Sidebar')).toBeNull();
  });

  it('renders work mode and reveals asset sidebar', () => {
    useWorkLayoutStore.setState({ viewMode: 'work' });

    render(
      <DualModeContainer>
        <div data-testid="chat-viewport">Chat Viewport Body</div>
      </DualModeContainer>,
    );

    const container = screen.getByTestId('dual-mode-container');
    expect(container.getAttribute('data-mode')).toBe('work');

    expect(screen.getByLabelText('Work Assets Sidebar')).toBeDefined();
    expect(screen.getByTestId('chat-viewport')).toBeDefined();
  });

  it('renders custom headerSlot when provided', () => {
    render(
      <DualModeContainer headerSlot={<span data-testid="custom-session-title">Session #42</span>}>
        <div>Body</div>
      </DualModeContainer>,
    );

    expect(screen.getByTestId('custom-session-title')).toBeDefined();
  });
});
