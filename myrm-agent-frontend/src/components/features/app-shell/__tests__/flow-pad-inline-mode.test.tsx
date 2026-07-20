/** @vitest-environment jsdom */
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useFlowPadStore } from '@/store/useFlowPadStore';

type Listener = (state: Record<string, unknown>, prev: Record<string, unknown>) => void;

let subscribers: Listener[] = [];
const mockChatState = {
  agentConfig: { name: 'TestAgent' },
  sendMessage: vi.fn().mockResolvedValue(undefined),
  setFiles: vi.fn(),
  files: [],
  messages: [] as Array<{ role: string; content: string }>,
  loading: false,
};
const mockAgentStoreState = {
  agents: [
    {
      id: 'builtin-general',
      name: 'General Agent',
      avatar_url: '',
    },
    {
      id: 'writer-agent',
      name: 'Writer Agent',
      avatar_url: '',
    },
  ],
  loading: false,
  fetchAgents: vi.fn().mockResolvedValue(undefined),
  fetchAgent: vi.fn().mockImplementation(async (agentId: string) => ({
    id: agentId,
    user_id: 'user-1',
    name: agentId === 'writer-agent' ? 'Writer Agent' : 'General Agent',
    system_prompt: agentId === 'writer-agent' ? 'Write with concise style.' : '',
    skill_ids: agentId === 'writer-agent' ? ['writing'] : [],
    mcp_ids: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  })),
};

vi.mock('@/store/useChatStore', () => {
  const hook = vi.fn(() => mockChatState);
  Object.assign(hook, {
    getState: () => mockChatState,
    subscribe: (listener: Listener) => {
      subscribers.push(listener);
      return () => {
        subscribers = subscribers.filter((l) => l !== listener);
      };
    },
    setState: vi.fn(),
    destroy: vi.fn(),
  });
  return { default: hook };
});

vi.mock('@/store/useAgentStore', () => {
  const hook = <T,>(selector?: (state: typeof mockAgentStoreState) => T): T =>
    selector ? selector(mockAgentStoreState) : (mockAgentStoreState as unknown as T);
  Object.assign(hook, {
    getState: () => mockAgentStoreState,
    setState: vi.fn(),
    subscribe: vi.fn(),
    destroy: vi.fn(),
  });
  return { default: hook };
});

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@radix-ui/react-visually-hidden', () => ({
  VisuallyHidden: ({ children }: { children: React.ReactNode }) => (
    <span style={{ display: 'none' }}>{children}</span>
  ),
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => false,
  isLocalMode: () => true,
  getDeployMode: () => 'local',
  isSandbox: () => false,
  isSandboxAuthBuild: () => false,
  shouldRedirectToLoginOnAuthFailure: () => false,
  getLocalUserId: () => 'test-user',
  getApiBaseUrl: () => 'http://localhost:8000/api',
  getBackendBaseUrl: () => 'http://localhost:8000',
  getDocsUrl: () => 'http://localhost:3001',
  normalizeConfiguredBaseUrl: (val: string) => val || 'http://localhost:8000',
}));

import { FlowPadModal } from '../flow-pad-modal';

function simulateChatStoreChange(partial: Partial<typeof mockChatState>) {
  const prev = { ...mockChatState };
  Object.assign(mockChatState, partial);
  for (const listener of subscribers) {
    listener(mockChatState, prev);
  }
}

describe('FlowPadModal - Inline Mode Integration', () => {
  beforeEach(() => {
    useFlowPadStore.getState().close();
    mockChatState.messages = [];
    mockChatState.loading = false;
    subscribers = [];
    mockAgentStoreState.loading = false;
    mockAgentStoreState.fetchAgents.mockClear();
    mockAgentStoreState.fetchAgent.mockClear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    subscribers = [];
  });

  it('subscribes to useChatStore when entering inline mode', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      100,
    );

    render(<FlowPadModal />);

    expect(subscribers.length).toBe(1);
  });

  it('does NOT subscribe when in chat mode', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);
    expect(subscribers.length).toBe(0);
  });

  it('bridges streaming messages to inlineResult', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'VS Code', extractedText: '', timestamp: 1 },
      200,
    );
    render(<FlowPadModal />);

    act(() => {
      simulateChatStoreChange({
        loading: true,
        messages: [{ role: 'assistant', content: 'Hello' }],
      });
    });

    expect(useFlowPadStore.getState().inlineResult).toBe('Hello');
    expect(useFlowPadStore.getState().inlineGenerating).toBe(true);
  });

  it('updates inlineResult progressively during streaming', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      300,
    );
    render(<FlowPadModal />);

    act(() => {
      simulateChatStoreChange({
        loading: true,
        messages: [{ role: 'assistant', content: 'He' }],
      });
    });
    expect(useFlowPadStore.getState().inlineResult).toBe('He');

    act(() => {
      simulateChatStoreChange({
        messages: [{ role: 'assistant', content: 'Hello world' }],
      });
    });
    expect(useFlowPadStore.getState().inlineResult).toBe('Hello world');
  });

  it('sets inlineGenerating=false when loading transitions to false', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      400,
    );
    render(<FlowPadModal />);

    act(() => {
      simulateChatStoreChange({
        loading: true,
        messages: [{ role: 'assistant', content: 'Done.' }],
      });
    });
    expect(useFlowPadStore.getState().inlineGenerating).toBe(true);

    act(() => {
      simulateChatStoreChange({ loading: false });
    });
    expect(useFlowPadStore.getState().inlineGenerating).toBe(false);
    expect(useFlowPadStore.getState().inlineResult).toBe('Done.');
  });

  it('unsubscribes when modal closes', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      500,
    );
    const { rerender } = render(<FlowPadModal />);
    expect(subscribers.length).toBe(1);

    act(() => {
      useFlowPadStore.getState().close();
    });
    rerender(<FlowPadModal />);

    expect(subscribers.length).toBe(0);
  });

  it('ignores changes when both loading states are false', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      600,
    );
    render(<FlowPadModal />);

    act(() => {
      simulateChatStoreChange({
        messages: [{ role: 'user', content: 'Question' }],
      });
    });

    expect(useFlowPadStore.getState().inlineResult).toBe('');
    expect(useFlowPadStore.getState().inlineGenerating).toBe(false);
  });

  it('only picks last assistant message (ignores user messages)', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      700,
    );
    render(<FlowPadModal />);

    act(() => {
      simulateChatStoreChange({
        loading: true,
        messages: [
          { role: 'user', content: 'What is this?' },
          { role: 'assistant', content: 'It is a test.' },
        ],
      });
    });

    expect(useFlowPadStore.getState().inlineResult).toBe('It is a test.');
  });

  it('displays streaming result text in the UI', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      800,
    );
    useFlowPadStore.setState({ inlineResult: 'Visible result text', inlineGenerating: false });

    render(<FlowPadModal />);

    expect(screen.getByText('Visible result text')).toBeInTheDocument();
  });

  it('shows Paste and Copy buttons when inlineResult exists', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      900,
    );
    useFlowPadStore.setState({ inlineResult: 'Some result', inlineGenerating: false });

    render(<FlowPadModal />);

    expect(screen.getByText('pasteBack')).toBeInTheDocument();
    expect(screen.getByText('copyResult')).toBeInTheDocument();
  });

  it('shows loading spinner when inlineGenerating is true and content exists', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1000,
    );
    useFlowPadStore.setState({ inlineResult: 'Partial result...', inlineGenerating: true });

    render(<FlowPadModal />);

    expect(screen.getByText('generating')).toBeInTheDocument();
  });

  it('does not show result section when inlineResult is empty', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1100,
    );
    useFlowPadStore.setState({ inlineResult: '', inlineGenerating: true });

    render(<FlowPadModal />);

    expect(screen.queryByText('generating')).not.toBeInTheDocument();
    expect(screen.queryByText('pasteBack')).not.toBeInTheDocument();
  });

  it('keeps modal open after submit in inline mode (for paste-back)', async () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'VS Code', extractedText: 'some text', timestamp: 1 },
      1200,
    );
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Explain this' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockChatState.sendMessage).toHaveBeenCalledTimes(1);
    expect(useFlowPadStore.getState().isOpen).toBe(true);
    expect(useFlowPadStore.getState().mode).toBe('inline');
  });

  it('hides Paste/Copy buttons while still generating', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1300,
    );
    useFlowPadStore.setState({ inlineResult: 'Partial...', inlineGenerating: true });

    render(<FlowPadModal />);

    expect(screen.queryByText('pasteBack')).not.toBeInTheDocument();
    expect(screen.queryByText('copyResult')).not.toBeInTheDocument();
    expect(screen.getByText('generating')).toBeInTheDocument();
  });

  it('picks the LAST assistant message when multiple exist', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1400,
    );
    render(<FlowPadModal />);

    act(() => {
      simulateChatStoreChange({
        loading: true,
        messages: [
          { role: 'assistant', content: 'Old response' },
          { role: 'user', content: 'Follow up' },
          { role: 'assistant', content: 'Latest response' },
        ],
      });
    });

    expect(useFlowPadStore.getState().inlineResult).toBe('Latest response');
  });

  it('shows inline-specific placeholder text', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1500,
    );
    render(<FlowPadModal />);

    expect(screen.getByPlaceholderText('inlinePlaceholder')).toBeInTheDocument();
  });

  it('shows Inline badge in header', () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1600,
    );
    render(<FlowPadModal />);

    expect(screen.getByText('Inline')).toBeInTheDocument();
    expect(screen.getAllByText('inlineTitle')).toHaveLength(2);
  });

  it('handleCopyResult copies to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1700,
    );
    useFlowPadStore.setState({ inlineResult: 'Copy this text', inlineGenerating: false });

    render(<FlowPadModal />);

    const copyBtn = screen.getByText('copyResult');
    await act(async () => {
      copyBtn.click();
    });

    expect(writeTextMock).toHaveBeenCalledWith('Copy this text');
  });

  it('routes inline send with selected agent profile config', async () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: 'ctx', timestamp: 1 },
      1800,
    );
    render(<FlowPadModal />);

    const switcherTrigger = screen.getByTestId('flowpad-inline-route-trigger');
    await act(async () => {
      switcherTrigger.click();
    });

    const writerOption = await screen.findByTestId('flowpad-inline-route-agent-writer-agent');
    await act(async () => {
      writerOption.click();
    });

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Route this request' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockChatState.sendMessage).toHaveBeenCalledTimes(1);
    expect(mockAgentStoreState.fetchAgent).toHaveBeenCalledWith('writer-agent');
    const sendArgs = mockChatState.sendMessage.mock.calls[0];
    expect(sendArgs[0]).toContain('Route this request');
    expect(sendArgs[5]).toMatchObject({
      agentId: 'writer-agent',
      selectedSkillIds: ['writing'],
      systemPrompt: 'Write with concise style.',
    });
  });

  it('can reset to follow current session routing', async () => {
    useFlowPadStore.getState().openInline(
      { screenshot: '', windowTitle: 'App', extractedText: '', timestamp: 1 },
      1900,
    );
    render(<FlowPadModal />);

    const switcherTrigger = screen.getByTestId('flowpad-inline-route-trigger');
    await act(async () => {
      switcherTrigger.click();
    });
    const writerOption = await screen.findByTestId('flowpad-inline-route-agent-writer-agent');
    await act(async () => {
      writerOption.click();
    });
    await screen.findByText('inlineRouteProfile');

    const selectedTrigger = screen.getByTestId('flowpad-inline-route-trigger');
    await act(async () => {
      selectedTrigger.click();
    });
    const followCurrentOption = await screen.findByTestId('flowpad-inline-route-follow-current');
    await act(async () => {
      followCurrentOption.click();
    });

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Use current route' } });
    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockChatState.sendMessage).toHaveBeenCalledTimes(1);
    expect(mockChatState.sendMessage.mock.calls[0]).toEqual(['Use current route']);
  });
});
