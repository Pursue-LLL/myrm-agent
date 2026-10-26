import { describe, expect, it, vi, beforeEach } from 'vitest';
import { executeTerminalCommand } from '../workbench';
import { apiClient } from '../api';

vi.mock('../api', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

describe('workbench service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('executeTerminalCommand runs the command in the named chat workspace', async () => {
    const mockExec = {
      command: 'echo ok',
      exit_code: 0,
      stdout: 'ok\n',
      stderr: '',
      duration_ms: 15,
      truncated: false,
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockExec);

    const result = await executeTerminalCommand('chat-1', 'echo ok', 'src', 15);
    expect(apiClient.post).toHaveBeenCalledWith('/workbench/terminal/exec', {
      chat_id: 'chat-1',
      command: 'echo ok',
      cwd: 'src',
      timeout_seconds: 15,
    });
    expect(result).toEqual(mockExec);
  });
});
