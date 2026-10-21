import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  fetchWorkspaceFiles,
  fetchFileContent,
  computeFileDiff,
  executeTerminalCommand,
  fetchWorkbenchPlugins,
  probePluginHealth,
} from '../workbench';
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

  it('fetchWorkspaceFiles queries files endpoint with params', async () => {
    const mockTree = {
      root_path: '/workspace',
      nodes: [],
      total_files: 0,
      total_dirs: 0,
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockTree);

    const result = await fetchWorkspaceFiles('src', 4);
    expect(apiClient.get).toHaveBeenCalledWith('/workbench/files?max_depth=4&root_dir=src');
    expect(result).toEqual(mockTree);
  });

  it('fetchFileContent queries file content by path', async () => {
    const mockContent = {
      path: 'src/main.py',
      content: 'print("hello")',
      language: 'python',
      size_bytes: 14,
      is_binary: false,
      modified_at: '2026-10-12T10:00:00Z',
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockContent);

    const result = await fetchFileContent('src/main.py');
    expect(apiClient.get).toHaveBeenCalledWith('/workbench/file/content?path=src%2Fmain.py');
    expect(result).toEqual(mockContent);
  });

  it('computeFileDiff posts diff request payload', async () => {
    const mockDiff = {
      file_path: 'app.ts',
      unified_diff: '@@ -1 +1 @@\n-old\n+new',
      additions: 1,
      deletions: 1,
      hunks: [],
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockDiff);

    const req = { file_path: 'app.ts', original_content: 'old', modified_content: 'new' };
    const result = await computeFileDiff(req);
    expect(apiClient.post).toHaveBeenCalledWith('/workbench/diff', req);
    expect(result).toEqual(mockDiff);
  });

  it('executeTerminalCommand sends command to terminal exec endpoint', async () => {
    const mockExec = {
      command: 'echo ok',
      exit_code: 0,
      stdout: 'ok\n',
      stderr: '',
      duration_ms: 15,
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockExec);

    const result = await executeTerminalCommand('echo ok', '/workspace', 15);
    expect(apiClient.post).toHaveBeenCalledWith('/workbench/terminal/exec', {
      command: 'echo ok',
      cwd: '/workspace',
      timeout_seconds: 15,
    });
    expect(result).toEqual(mockExec);
  });

  it('fetchWorkbenchPlugins and probePluginHealth call correct endpoints', async () => {
    const mockPlugins = [
      {
        plugin_id: 'p1',
        name: 'Diff Inspector',
        description: 'Diff inspection tool',
        version: '1.0.0',
        author: 'Myrm',
        status: 'healthy' as const,
        is_installed: true,
      },
    ];
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockPlugins);

    const plugins = await fetchWorkbenchPlugins();
    expect(apiClient.get).toHaveBeenCalledWith('/workbench/plugins');
    expect(plugins).toEqual(mockPlugins);

    const mockProbe = {
      plugin_id: 'p1',
      status: 'healthy' as const,
      latency_ms: 10,
      message: 'Probe ok',
      details: {},
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockProbe);

    const probe = await probePluginHealth('p1');
    expect(apiClient.post).toHaveBeenCalledWith('/workbench/plugins/p1/probe', {});
    expect(probe).toEqual(mockProbe);
  });
});
