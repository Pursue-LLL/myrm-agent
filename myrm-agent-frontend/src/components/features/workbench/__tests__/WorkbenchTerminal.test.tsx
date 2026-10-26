/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchTerminal } from '../tabs/WorkbenchTerminal';
import { ApiError } from '@/lib/api';
import useChatStore from '@/store/useChatStore';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import * as workbenchService from '@/services/workbench';

const toastSuccess = vi.hoisted(() => vi.fn());

vi.mock('sonner', () => ({ toast: { success: toastSuccess } }));

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join(',')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/workbench', () => ({
  TERMINAL_TIMEOUT_SECONDS: 30,
  executeTerminalCommand: vi.fn(),
}));

describe('WorkbenchTerminal component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkbenchStore.setState({
      terminalLogs: [],
    });
    useChatStore.setState({ chatId: 'chat-1', inputMessage: '' });
    vi.mocked(workbenchService.executeTerminalCommand).mockResolvedValue({
      command: 'echo hello',
      stdout: 'hello\n',
      stderr: '',
      exit_code: 0,
      duration_ms: 12,
      truncated: false,
    });
  });

  it('renders empty terminal hint when logs are empty', () => {
    render(<WorkbenchTerminal chatId="chat-1" />);

    expect(screen.getByText('emptyTerminalHint')).toBeDefined();
    expect(screen.getByPlaceholderText('inputPlaceholder')).toBeDefined();
  });

  it('renders existing terminal logs with exit code badges', () => {
    useWorkbenchStore.setState({
      terminalLogs: [
        {
          id: 'log-1',
          command: 'ls -la',
          output: 'total 0\nfile.txt',
          exitCode: 0,
          timestamp: '2023-11-14T22:13:20Z',
        },
        {
          id: 'log-2',
          command: 'cat missing.txt',
          output: 'No such file or directory',
          exitCode: 1,
          timestamp: '2023-11-14T22:13:21Z',
        },
      ],
    });

    render(<WorkbenchTerminal chatId="chat-1" />);

    expect(screen.getByText('ls -la')).toBeDefined();
    expect(screen.getByText(/total 0/)).toBeDefined();
    expect(screen.getByText('exitCode:0')).toBeDefined();

    expect(screen.getByText('cat missing.txt')).toBeDefined();
    expect(screen.getByText('exitCode:1')).toBeDefined();
  });

  it('executes command when clicking run button', async () => {
    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'echo hello' } });

    const runBtn = screen.getByRole('button', { name: /runAction/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(workbenchService.executeTerminalCommand).toHaveBeenCalledWith('chat-1', 'echo hello');
      expect(screen.getByText('echo hello')).toBeDefined();
      expect(screen.getAllByText(/hello/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('executes command on Enter key press', async () => {
    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'echo enter' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(workbenchService.executeTerminalCommand).toHaveBeenCalledWith('chat-1', 'echo enter');
    });
  });

  const failures: Array<[string, unknown, string]> = [
    ['a command the safety guard refused', new ApiError('Command rejected by safety guard: rm -rf /', 400), 'blocked'],
    ['a chat without a workspace folder', new ApiError('Workspace directory not found', 404), 'workspaceUnavailable'],
    ['a command the server stopped', new ApiError('Command execution timed out after 30s', 408), 'timedOut:30'],
    [
      'a request that ran out of time',
      new ApiError('request timeout', 40408, [], undefined, 'TIMEOUT_ERROR'),
      'timedOut:30',
    ],
    ['a server error', new ApiError('Execution error: [Errno 2] No such file', 500), 'runFailed'],
    ['an unexpected error', new Error('Command failed: 127'), 'runFailed'],
  ];

  it.each(failures)('explains %s in the history without a raw message or an exit code', async (_name, error, text) => {
    vi.mocked(workbenchService.executeTerminalCommand).mockRejectedValueOnce(error);
    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'bad_cmd' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => expect(screen.getByText(text)).toBeDefined());
    expect(screen.getByText('failedBadge')).toBeDefined();
    expect(screen.queryByText(/exitCode/)).toBeNull();
    expect(screen.queryByText(/Errno|safety guard|127/)).toBeNull();
    expect(useWorkbenchStore.getState().terminalLogs[0].exitCode).toBeNull();
    expect(screen.queryByRole('button', { name: 'injectToChat' })).toBeNull();
  });

  it('says so when the output was cut', async () => {
    vi.mocked(workbenchService.executeTerminalCommand).mockResolvedValueOnce({
      command: 'yes',
      stdout: 'y\n',
      stderr: '',
      exit_code: 0,
      duration_ms: 12,
      truncated: true,
    });

    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'yes' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText(/outputTruncated/)).toBeDefined();
    });
  });

  it('does not log output that arrives after the workspace session was reset', async () => {
    let finish: (value: workbenchService.TerminalExecResponse) => void = () => {};
    vi.mocked(workbenchService.executeTerminalCommand).mockImplementationOnce(
      () => new Promise((resolve) => (finish = resolve)),
    );
    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'sleep 5' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    act(() => useWorkbenchStore.getState().resetWorkspaceSession());
    await act(async () =>
      finish({ command: 'sleep 5', stdout: 'old chat', stderr: '', exit_code: 0, duration_ms: 5, truncated: false }),
    );

    expect(useWorkbenchStore.getState().terminalLogs).toHaveLength(0);
  });

  it('shows a placeholder when a command prints nothing', async () => {
    vi.mocked(workbenchService.executeTerminalCommand).mockResolvedValueOnce({
      command: 'true',
      stdout: '',
      stderr: '',
      exit_code: 0,
      duration_ms: 3,
      truncated: false,
    });

    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'true' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('noOutput')).toBeDefined();
    });
  });

  it('clears terminal logs when clear button is clicked', () => {
    useWorkbenchStore.setState({
      terminalLogs: [
        {
          id: 'log-1',
          command: 'ls',
          output: 'out',
          exitCode: 0,
          timestamp: '2023-11-14T22:13:20Z',
        },
      ],
    });

    render(<WorkbenchTerminal chatId="chat-1" />);

    const clearBtn = screen.getByRole('button', { name: /clearAction/i });
    fireEvent.click(clearBtn);

    expect(useWorkbenchStore.getState().terminalLogs).toHaveLength(0);
  });

  describe('handing output to the chat input', () => {
    const logGitStatus = () =>
      useWorkbenchStore.setState({
        terminalLogs: [
          {
            id: 'log-1',
            command: 'git status',
            output: 'On branch main',
            exitCode: 0,
            timestamp: '2023-11-14T22:13:20Z',
          },
        ],
      });

    it('puts the command and its output into the chat input and says so', () => {
      logGitStatus();
      render(<WorkbenchTerminal chatId="chat-1" />);

      fireEvent.click(screen.getByRole('button', { name: 'injectToChat' }));

      expect(useChatStore.getState().inputMessage).toBe('```bash\n$ git status\nOn branch main\n```\n');
      expect(toastSuccess).toHaveBeenCalledWith('injected');
    });

    it('keeps what the user had already typed', () => {
      useChatStore.setState({ inputMessage: 'why does this fail?' });
      logGitStatus();
      render(<WorkbenchTerminal chatId="chat-1" />);

      fireEvent.click(screen.getByRole('button', { name: 'injectToChat' }));

      expect(useChatStore.getState().inputMessage).toBe(
        'why does this fail?\n\n```bash\n$ git status\nOn branch main\n```\n',
      );
    });
  });
});
