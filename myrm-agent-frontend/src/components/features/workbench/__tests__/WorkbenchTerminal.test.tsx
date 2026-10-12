/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchTerminal } from '../tabs/WorkbenchTerminal';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import * as workbenchService from '@/services/workbench';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
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
    });
  });

  it('renders empty terminal hint when logs are empty', () => {
    render(<WorkbenchTerminal />);

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

    render(<WorkbenchTerminal />);

    expect(screen.getByText('ls -la')).toBeDefined();
    expect(screen.getByText(/total 0/)).toBeDefined();
    expect(screen.getByText('exit 0')).toBeDefined();

    expect(screen.getByText('cat missing.txt')).toBeDefined();
    expect(screen.getByText('exit 1')).toBeDefined();
  });

  it('executes command when clicking run button', async () => {
    render(<WorkbenchTerminal />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'echo hello' } });

    const runBtn = screen.getByRole('button', { name: /runAction/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(workbenchService.executeTerminalCommand).toHaveBeenCalledWith('echo hello');
      expect(screen.getByText('echo hello')).toBeDefined();
      expect(screen.getAllByText(/hello/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('executes command on Enter key press', async () => {
    render(<WorkbenchTerminal />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'echo enter' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(workbenchService.executeTerminalCommand).toHaveBeenCalledWith('echo enter');
    });
  });

  it('handles command failure gracefully with exit code 1', async () => {
    vi.mocked(workbenchService.executeTerminalCommand).mockRejectedValueOnce(
      new Error('Command failed: 127'),
    );

    render(<WorkbenchTerminal />);

    const input = screen.getByPlaceholderText('inputPlaceholder');
    fireEvent.change(input, { target: { value: 'bad_cmd' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText('Error: Command failed: 127')).toBeDefined();
      expect(screen.getByText('exit 1')).toBeDefined();
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

    render(<WorkbenchTerminal />);

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

    render(<WorkbenchTerminal />);

    const shareBtn = screen.getByTitle('injectToChat');
    fireEvent.click(shareBtn);

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('myrm:insert-to-chat');
    expect(event.detail.text).toContain('$ git status');
    expect(event.detail.text).toContain('On branch main');
  });
});
