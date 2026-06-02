import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest';

const mockSendMessage = vi.fn();
const mockEnqueue = vi.fn();
const mockWriteToClipboard = vi.fn();
const mockToastInfo = vi.fn();

let mockLoading = false;

vi.mock('@/store/useChatStore', () => {
  const getState = () => ({
    chatId: 'test-chat-1',
    loading: mockLoading,
    sendMessage: mockSendMessage,
  });
  const store = Object.assign((selector: (s: Record<string, unknown>) => unknown) => selector(getState()), {
    getState,
  });
  return { default: store };
});

let mockDirtyArtifacts: Record<string, string> = {};
const mockClearDirtyState = vi.fn();

vi.mock('@/store/useArtifactPortalStore', () => {
  const getState = () => ({
    getDirtyArtifacts: () => mockDirtyArtifacts,
    clearDirtyState: mockClearDirtyState,
  });
  const store = Object.assign(() => ({}), { getState });
  return { default: store };
});

vi.mock('@/hooks/useMessageQueue', () => ({
  useMessageQueue: () => ({
    enqueue: mockEnqueue,
    queue: [],
    hasQueuedMessages: false,
  }),
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  writeToClipboard: (...args: unknown[]) => mockWriteToClipboard(...args),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: (...args: unknown[]) => mockToastInfo(...args),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

vi.mock('hugeicons-react', () => ({
  Edit04Icon: (props: Record<string, unknown>) => <span data-testid="edit-icon" {...props} />,
  InformationCircleIcon: (props: Record<string, unknown>) => <span data-testid="info-icon" {...props} />,
  SparklesIcon: (props: Record<string, unknown>) => <span data-testid="sparkles-icon" {...props} />,
  MessageAdd01Icon: (props: Record<string, unknown>) => <span data-testid="message-icon" {...props} />,
  Copy01Icon: (props: Record<string, unknown>) => <span data-testid="copy-icon" {...props} />,
  ArrowRight01Icon: (props: Record<string, unknown>) => <span data-testid="arrow-icon" {...props} />,
}));

import SelectionToolbar from '../SelectionToolbar';
import type { editor } from 'monaco-editor';

type Callback = () => void;

function createMockEditor(
  overrides: Partial<{
    selection: {
      startLineNumber: number;
      endLineNumber: number;
      startColumn: number;
      endColumn: number;
      isEmpty: () => boolean;
    } | null;
    selectedText: string;
    domHeight: number;
    scrolledPosition: { top: number; left: number; height: number } | null;
  }> = {},
) {
  const selectionListeners: Callback[] = [];
  const scrollListeners: Callback[] = [];

  const defaultSelection =
    overrides.selection === null
      ? null
      : (overrides.selection ?? {
          startLineNumber: 5,
          endLineNumber: 8,
          startColumn: 1,
          endColumn: 10,
          isEmpty: () => false,
        });

  const mock = {
    getSelection: vi.fn(() => defaultSelection),
    getModel: vi.fn(() => ({
      getValueInRange: vi.fn(() => overrides.selectedText ?? 'const foo = "bar";'),
    })),
    getScrolledVisiblePosition: vi.fn(() => overrides.scrolledPosition ?? { top: 100, left: 50, height: 20 }),
    getDomNode: vi.fn(() => ({ clientHeight: overrides.domHeight ?? 600 })),
    onDidChangeCursorSelection: vi.fn((cb: Callback) => {
      selectionListeners.push(cb);
      return { dispose: vi.fn() };
    }),
    onDidScrollChange: vi.fn((cb: Callback) => {
      scrollListeners.push(cb);
      return { dispose: vi.fn() };
    }),
    _fireSelection: () => selectionListeners.forEach((cb) => cb()),
    _fireScroll: () => scrollListeners.forEach((cb) => cb()),
  };

  return mock as unknown as editor.IStandaloneCodeEditor & {
    _fireSelection: () => void;
    _fireScroll: () => void;
  };
}

function triggerSelection(editorMock: ReturnType<typeof createMockEditor>) {
  act(() => {
    editorMock._fireSelection();
    vi.advanceTimersByTime(300);
  });
}

describe('SelectionToolbar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockLoading = false;
    mockDirtyArtifacts = {};
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when no selection (isEmpty)', () => {
    const editorMock = createMockEditor({
      selection: {
        startLineNumber: 1,
        endLineNumber: 1,
        startColumn: 1,
        endColumn: 1,
        isEmpty: () => true,
      },
    });

    const { container } = render(
      <SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />,
    );

    triggerSelection(editorMock);
    expect(container.innerHTML).toBe('');
  });

  it('shows toolbar after text selection with debounce', () => {
    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    act(() => {
      editorMock._fireSelection();
    });
    expect(screen.queryAllByRole('button')).toHaveLength(0);

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getAllByRole('button')).toHaveLength(5);
  });

  it('displays all 5 action buttons with correct labels', () => {
    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    triggerSelection(editorMock);

    expect(screen.getByText('modify')).toBeDefined();
    expect(screen.getByText('explain')).toBeDefined();
    expect(screen.getByText('optimize')).toBeDefined();
    expect(screen.getByText('addComment')).toBeDefined();
    expect(screen.getByText('copy')).toBeDefined();
  });

  it('hides on scroll', () => {
    const editorMock = createMockEditor();

    const { container } = render(
      <SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />,
    );

    triggerSelection(editorMock);
    expect(screen.getAllByRole('button')).toHaveLength(5);

    act(() => {
      editorMock._fireScroll();
    });
    expect(container.innerHTML).toBe('');
  });

  it('hides on mobile viewport', () => {
    Object.defineProperty(window, 'innerWidth', { value: 400, writable: true });

    const editorMock = createMockEditor();

    const { container } = render(
      <SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />,
    );

    triggerSelection(editorMock);
    expect(container.innerHTML).toBe('');
  });

  it('sends explain action with selection_context', async () => {
    vi.useRealTimers();
    const editorMock = createMockEditor({
      selectedText: 'function hello() {}',
      selection: {
        startLineNumber: 10,
        endLineNumber: 12,
        startColumn: 1,
        endColumn: 2,
        isEmpty: () => false,
      },
    });

    mockSendMessage.mockResolvedValue(undefined);

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-42" language="javascript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('explain').closest('button')!);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('[explain]');
    expect(msg).toContain('lines 10-12');
    expect(msg).toContain(
      '<selection_context artifact_id="art-42" language="javascript" start_line="10" end_line="12">',
    );
    expect(msg).toContain('function hello() {}');
    expect(msg).toContain('</selection_context>');
  });

  it('sends single-line range format correctly', async () => {
    vi.useRealTimers();
    const editorMock = createMockEditor({
      selectedText: 'let x = 1;',
      selection: {
        startLineNumber: 5,
        endLineNumber: 5,
        startColumn: 1,
        endColumn: 11,
        isEmpty: () => false,
      },
    });

    mockSendMessage.mockResolvedValue(undefined);

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('optimize').closest('button')!);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('line 5');
    expect(msg).not.toContain('lines 5-5');
  });

  it('injects dirty artifacts into message', async () => {
    vi.useRealTimers();
    mockDirtyArtifacts = { 'dirty-1': 'modified code here' };
    mockSendMessage.mockResolvedValue(undefined);

    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('explain').closest('button')!);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('<edited_artifact id="dirty-1">');
    expect(msg).toContain('modified code here');
    expect(msg).toContain('</edited_artifact>');
    expect(mockClearDirtyState).toHaveBeenCalledWith('dirty-1');
  });

  it('enqueues message when agent is loading', async () => {
    vi.useRealTimers();
    mockLoading = true;

    const editorMock = createMockEditor();

    const { unmount } = render(
      <SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />,
    );

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('explain').closest('button')!);

    await waitFor(() => {
      expect(mockEnqueue).toHaveBeenCalledTimes(1);
    });
    expect(mockToastInfo).toHaveBeenCalledWith('queued');
    expect(mockSendMessage).not.toHaveBeenCalled();

    unmount();
    mockLoading = false;
  });

  it('enqueues on AgentBusyError', async () => {
    vi.useRealTimers();

    const busyError = new Error('Agent is busy');
    busyError.name = 'AgentBusyError';
    mockSendMessage.mockRejectedValue(busyError);

    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('explain').closest('button')!);

    await waitFor(() => {
      expect(mockEnqueue).toHaveBeenCalledTimes(1);
    });
    expect(mockToastInfo).toHaveBeenCalledWith('queued');
  });

  it('shows input box on modify click and submits with Enter', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    mockSendMessage.mockResolvedValue(undefined);

    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('modify').closest('button')!);

    const input = screen.getByPlaceholderText('modifyPlaceholder');
    expect(input).toBeDefined();

    await user.type(input, 'rename variables{enter}');

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledTimes(1);
    });

    const msg = mockSendMessage.mock.calls[0][0] as string;
    expect(msg).toContain('[modify]');
    expect(msg).toContain('rename variables');
  });

  it('copy button writes to clipboard', async () => {
    vi.useRealTimers();
    mockWriteToClipboard.mockResolvedValue(true);

    const editorMock = createMockEditor({ selectedText: 'copied text' });

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('copy').closest('button')!);

    await waitFor(() => {
      expect(mockWriteToClipboard).toHaveBeenCalledWith('copied text');
    });
  });

  it('closes input box on Escape key', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();

    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    vi.useFakeTimers();
    triggerSelection(editorMock);
    vi.useRealTimers();

    fireEvent.click(screen.getByText('modify').closest('button')!);

    const input = screen.getByPlaceholderText('modifyPlaceholder');
    await user.type(input, 'some text');
    await user.keyboard('{Escape}');

    expect(screen.queryByPlaceholderText('modifyPlaceholder')).toBeNull();
  });

  it('does not submit empty modify input', () => {
    const editorMock = createMockEditor();

    render(<SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />);

    triggerSelection(editorMock);

    fireEvent.click(screen.getByText('modify').closest('button')!);

    const submitBtn = screen.getByTestId('arrow-icon').closest('button')!;
    expect(submitBtn).toHaveAttribute('disabled');

    fireEvent.click(submitBtn);
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('positions toolbar above selection when near bottom', () => {
    const editorMock = createMockEditor({
      scrolledPosition: { top: 570, left: 50, height: 20 },
      domHeight: 600,
    });

    const { container } = render(
      <SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />,
    );

    triggerSelection(editorMock);

    const outerDiv = container.firstElementChild as HTMLElement;
    expect(outerDiv).toBeDefined();

    const topValue = parseInt(outerDiv.style.top);
    expect(topValue).toBeLessThan(570);
  });

  it('renders nothing when editorInstance is null', () => {
    const { container } = render(<SelectionToolbar editorInstance={null} artifactId="art-1" language="typescript" />);
    expect(container.innerHTML).toBe('');
  });

  it('hides toolbar when whitespace-only text selected', () => {
    const editorMock = createMockEditor({
      selectedText: '   \n\t  ',
      selection: {
        startLineNumber: 1,
        endLineNumber: 2,
        startColumn: 1,
        endColumn: 5,
        isEmpty: () => false,
      },
    });

    const { container } = render(
      <SelectionToolbar editorInstance={editorMock} artifactId="art-1" language="typescript" />,
    );

    triggerSelection(editorMock);
    expect(container.innerHTML).toBe('');
  });
});
