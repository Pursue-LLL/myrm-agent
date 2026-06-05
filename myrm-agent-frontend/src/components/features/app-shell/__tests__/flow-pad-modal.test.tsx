import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useFlowPadStore, type FlowPadCapture } from '@/store/useFlowPadStore';

const { mockSendMessage, mockSetFiles } = vi.hoisted(() => ({
  mockSendMessage: vi.fn().mockResolvedValue(undefined),
  mockSetFiles: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => {
  const state = {
    agentConfig: { name: 'TestAgent' },
    sendMessage: (...args: unknown[]) => mockSendMessage(...args),
    setFiles: (...args: unknown[]) => mockSetFiles(...args),
    files: [] as unknown[],
  };
  const hook = vi.fn(() => state);
  Object.assign(hook, {
    getState: () => state,
    subscribe: vi.fn(),
    setState: vi.fn(),
    destroy: vi.fn(),
  });
  return { default: hook };
});

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@radix-ui/react-visually-hidden', () => ({
  VisuallyHidden: ({ children }: { children: React.ReactNode }) => (
    <span style={{ display: 'none' }}>{children}</span>
  ),
}));

import { FlowPadModal } from '../flow-pad-modal';

function makeCapture(overrides: Partial<FlowPadCapture> = {}): FlowPadCapture {
  return {
    screenshot: 'dGVzdA==',
    windowTitle: 'Test Window',
    extractedText: 'Extracted text content',
    timestamp: Date.now(),
    ...overrides,
  };
}

describe('FlowPadModal', () => {
  beforeEach(() => {
    useFlowPadStore.getState().close();
    mockSendMessage.mockClear();
    mockSetFiles.mockClear();
  });

  it('renders nothing when closed', () => {
    const { container } = render(<FlowPadModal />);
    expect(container.querySelector('textarea')).toBeNull();
  });

  it('renders textarea when opened', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('shows initial text from store', () => {
    useFlowPadStore.getState().open('Hello from deep link');
    render(<FlowPadModal />);
    expect(screen.getByRole('textbox')).toHaveValue('Hello from deep link');
  });

  it('shows capture preview when captures exist', () => {
    useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'VS Code' }));
    render(<FlowPadModal />);
    expect(screen.getByText('VS Code')).toBeInTheDocument();
  });

  it('shows multiple capture previews', () => {
    useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Window A' }));
    useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Window B' }));
    render(<FlowPadModal />);
    expect(screen.getByText('Window A')).toBeInTheDocument();
    expect(screen.getByText('Window B')).toBeInTheDocument();
  });

  it('disables send button when empty text and no captures', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);
    const buttons = screen.getAllByRole('button');
    const sendButton = buttons.find((b) => b.classList.contains('h-8'));
    expect(sendButton).toBeDisabled();
  });

  it('enables send button when text is entered', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Some question' } });

    const buttons = screen.getAllByRole('button');
    const sendButton = buttons.find((b) => b.classList.contains('h-8'));
    expect(sendButton).not.toBeDisabled();
  });

  it('enables send button when captures exist without text', () => {
    useFlowPadStore.getState().addCapture(makeCapture());
    render(<FlowPadModal />);

    const buttons = screen.getAllByRole('button');
    const sendButton = buttons.find((b) => b.classList.contains('h-8'));
    expect(sendButton).not.toBeDisabled();
  });

  it('calls sendMessage on Enter key (non-composing)', async () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Test question' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    expect(mockSendMessage).toHaveBeenCalledWith(expect.stringContaining('Test question'));
  });

  it('does NOT send on Enter during IME composition', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '你好' } });

    const event = new KeyboardEvent('keydown', {
      key: 'Enter',
      code: 'Enter',
      bubbles: true,
      cancelable: true,
    });
    Object.defineProperty(event, 'isComposing', { value: true });
    textarea.dispatchEvent(event);

    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('does NOT send on Shift+Enter', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Test' } });

    fireEvent.keyDown(textarea, {
      key: 'Enter',
      code: 'Enter',
      shiftKey: true,
      nativeEvent: { isComposing: false },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('closes modal after successful submit', async () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Test' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(useFlowPadStore.getState().isOpen).toBe(false);
  });

  it('includes appshot context in message when captures exist', async () => {
    useFlowPadStore.getState().addCapture(
      makeCapture({
        windowTitle: 'Terminal',
        extractedText: 'npm install completed',
      }),
    );
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'What happened?' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockSendMessage).toHaveBeenCalledWith(
      expect.stringContaining('[Appshot Context]'),
    );
    expect(mockSendMessage).toHaveBeenCalledWith(
      expect.stringContaining('**Terminal**'),
    );
    expect(mockSendMessage).toHaveBeenCalledWith(
      expect.stringContaining('npm install completed'),
    );
    expect(mockSendMessage).toHaveBeenCalledWith(
      expect.stringContaining('What happened?'),
    );
  });

  it('attaches screenshot files via setFiles when captures have screenshots', async () => {
    useFlowPadStore.getState().addCapture(makeCapture({ screenshot: 'abc123' }));
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Look at this' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockSetFiles).toHaveBeenCalledTimes(1);
    const filesArg = mockSetFiles.mock.calls[0][0];
    expect(filesArg).toHaveLength(1);
    expect(filesArg[0].fileName).toBe('appshot_1.jpg');
    expect(filesArg[0].fileUrl).toContain('abc123');
  });

  it('shows agent indicator when agentConfig has name', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);
    expect(screen.getByText('TestAgent')).toBeInTheDocument();
  });

  it('does not call sendMessage when both text and captures are empty', async () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('does not call setFiles when captures have no screenshots', async () => {
    useFlowPadStore.getState().addCapture(
      makeCapture({ screenshot: '', extractedText: 'text only' }),
    );
    render(<FlowPadModal />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Send this' } });

    await act(async () => {
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        code: 'Enter',
        nativeEvent: { isComposing: false },
      });
    });

    expect(mockSetFiles).not.toHaveBeenCalled();
    expect(mockSendMessage).toHaveBeenCalledTimes(1);
  });

  it('sends captures-only message without user text', async () => {
    useFlowPadStore.getState().addCapture(
      makeCapture({ windowTitle: 'Browser', extractedText: 'Page content' }),
    );
    render(<FlowPadModal />);

    const buttons = screen.getAllByRole('button');
    const sendButton = buttons.find((b) => b.classList.contains('h-8'));

    await act(async () => {
      sendButton?.click();
    });

    expect(mockSendMessage).toHaveBeenCalledTimes(1);
    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('[Appshot Context]');
    expect(msg).toContain('**Browser**');
    expect(msg).not.toContain('Page content\n\n');
  });

  it('shows correct placeholder text based on capture state', () => {
    useFlowPadStore.getState().open();
    render(<FlowPadModal />);
    expect(screen.getByPlaceholderText('placeholder')).toBeInTheDocument();
  });

  it('shows capture-specific placeholder when captures exist', () => {
    useFlowPadStore.getState().addCapture(makeCapture());
    render(<FlowPadModal />);
    expect(screen.getByPlaceholderText('placeholderWithCapture')).toBeInTheDocument();
  });
});
