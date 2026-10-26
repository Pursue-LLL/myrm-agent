import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fetchWorkspaceFiles, fetchFileContent, executeTerminalCommand } from '../workbench';
import { apiClient } from '../api';

vi.mock('../api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('workbench service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetchWorkspaceFiles names the chat whose workspace it browses', async () => {
    const mockTree = {
      root_path: '/workspace',
      nodes: [],
      total_files: 0,
      total_dirs: 0,
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockTree);

    const result = await fetchWorkspaceFiles('chat-1', 'src', 4);
    expect(apiClient.get).toHaveBeenCalledWith('/workbench/files?chat_id=chat-1&max_depth=4&root_dir=src');
    expect(result).toEqual(mockTree);
  });

  it('fetchFileContent reads a path inside the named chat workspace', async () => {
    const mockContent = {
      path: 'src/main.py',
      content: 'print("hello")',
      language: 'python',
      size_bytes: 14,
      is_binary: false,
      modified_at: '2026-10-12T10:00:00Z',
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockContent);

    const result = await fetchFileContent('chat-1', 'src/main.py');
    expect(apiClient.get).toHaveBeenCalledWith('/workbench/file/content?chat_id=chat-1&path=src%2Fmain.py');
    expect(result).toEqual(mockContent);
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
