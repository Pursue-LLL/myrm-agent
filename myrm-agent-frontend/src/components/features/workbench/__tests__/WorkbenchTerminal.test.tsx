/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchTerminal } from '../tabs/WorkbenchTerminal';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import * as workbenchService from '@/services/workbench';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values && 'message' in values ? `${key}:${String(values.message)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/workbench', () => ({
  executeTerminalCommand: vi.fn(),
}));

describe('WorkbenchTerminal component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkbenchStore.setState({
      terminalLogs: [],
    });
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
    expect(screen.getByText('exit 0')).toBeDefined();

    expect(screen.getByText('cat missing.txt')).toBeDefined();
    expect(screen.getByText('exit 1')).toBeDefined();
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

  it('handles command failure gracefully with exit code 1', async () => {
    vi.mocked(workbenchService.executeTerminalCommand).mockRejectedValueOnce(
      new Error('Command failed: 127'),
    );

    render(<WorkbenchTerminal chatId="chat-1" />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'bad_cmd' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('runFailed:Command failed: 127')).toBeDefined();
      expect(screen.getByText('exit 1')).toBeDefined();
    });
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

  it('dispatches custom event myrm:insert-to-chat when share button is clicked', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

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

    render(<WorkbenchTerminal chatId="chat-1" />);

    const shareBtn = screen.getByTitle('injectToChat');
    fireEvent.click(shareBtn);

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('myrm:insert-to-chat');
    expect(event.detail.text).toContain('$ git status');
    expect(event.detail.text).toContain('On branch main');
  });
});
