import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentConfig } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import ExtensionDisconnectedBanner from '../ExtensionDisconnectedBanner';

const kit = vi.hoisted(() => ({ badges: { extensionConnected: false } }));

vi.mock('@/hooks/shell/useNavBadges', () => ({ useNavBadges: () => kit.badges }));

const agentConfig = (browserSource?: string): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  browserSource,
});

const useBrowserSource = (browserSource?: string) => useChatStore.setState({ agentConfig: agentConfig(browserSource) });

beforeEach(() => {
  kit.badges = { extensionConnected: false };
  useChatStore.setState({ agentConfig: null });
});

afterEach(cleanup);

describe('ExtensionDisconnectedBanner', () => {
  it('warns that the extension is missing when the agent browses through it', () => {
    useBrowserSource('extension');
    render(<ExtensionDisconnectedBanner />);

    expect(screen.getByRole('alert')).toHaveTextContent('message');
    expect(screen.getByRole('link', { name: 'connect' })).toHaveAttribute('href', '/settings/extensionBridge');
  });

  it.each([
    ['another browser source', 'managed'],
    ['no browser source', undefined],
  ])('says nothing for %s', (_what, source) => {
    useBrowserSource(source);
    const { container } = render(<ExtensionDisconnectedBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('says nothing without an agent', () => {
    const { container } = render(<ExtensionDisconnectedBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('says nothing while the extension is connected', () => {
    useBrowserSource('extension');
    kit.badges = { extensionConnected: true };
    const { container } = render(<ExtensionDisconnectedBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('can be dismissed', () => {
    useBrowserSource('extension');
    const { container } = render(<ExtensionDisconnectedBanner />);

    fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

    expect(container).toBeEmptyDOMElement();
  });

  it('stays dismissed while the extension stays disconnected', () => {
    useBrowserSource('extension');
    const { container, rerender } = render(<ExtensionDisconnectedBanner />);
    fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

    act(() => useBrowserSource('extension'));
    rerender(<ExtensionDisconnectedBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('warns again when the extension connects and later drops', () => {
    useBrowserSource('extension');
    const { container, rerender } = render(<ExtensionDisconnectedBanner />);
    fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));

    kit.badges = { extensionConnected: true };
    rerender(<ExtensionDisconnectedBanner />);
    expect(container).toBeEmptyDOMElement();

    kit.badges = { extensionConnected: false };
    rerender(<ExtensionDisconnectedBanner />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
