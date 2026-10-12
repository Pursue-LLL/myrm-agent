import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../api';
import {
  executeSystemAssistantCommand,
  getSystemAssistantStatus,
  type SystemAssistantCommandRequest,
  type SystemAssistantCommandResponse,
  type SystemAssistantStatusResponse,
} from '../systemAssistant';

vi.mock('../api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('systemAssistant service client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('executeSystemAssistantCommand sends POST payload to /system-assistant/command', async () => {
    const mockRequest: SystemAssistantCommandRequest = {
      user_prompt: '帮我创建一个前端重构项目',
    };

    const mockResponse: SystemAssistantCommandResponse = {
      command_id: 'cmd-999',
      intent: 'create_project',
      summary: '已成功为您创建前端重构项目',
      action: {
        action_type: 'project_created',
        status: 'success',
        details: { project_id: 'proj-123' },
      },
      suggested_followups: ['查看新项目详情', '委派主力 Agent'],
      created_at: '2026-10-12T07:00:00Z',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

    const result = await executeSystemAssistantCommand(mockRequest);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/system-assistant/command',
      mockRequest,
    );
    expect(result).toEqual(mockResponse);
  });

  it('getSystemAssistantStatus fetches status from /system-assistant/status', async () => {
    const mockStatus: SystemAssistantStatusResponse = {
      active_agents_count: 2,
      running_tasks_count: 2,
      total_projects_count: 3,
      system_health: 'optimal',
      voice_enabled: true,
      last_heartbeat: '2026-10-12T07:00:00Z',
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockStatus);

    const result = await getSystemAssistantStatus();

    expect(apiClient.get).toHaveBeenCalledWith('/system-assistant/status');
    expect(result).toEqual(mockStatus);
    expect(result.voice_enabled).toBe(true);
  });
});
