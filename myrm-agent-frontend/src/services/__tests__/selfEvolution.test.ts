import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../api';
import {
  createSelfEvolutionTask,
  listSelfEvolutionTasks,
  recoverSelfEvolution,
  type SelfEvolutionTaskCreateRequest,
  type SelfEvolutionTaskResponse,
  type SelfEvolutionRecoverResponse,
} from '../selfEvolution';

vi.mock('../api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('selfEvolution service client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('createSelfEvolutionTask sends POST payload to /self-evolution/tasks', async () => {
    const mockRequest: SelfEvolutionTaskCreateRequest = {
      dom_selector: '#mobile-hub > div.card',
      tag_name: 'div',
      classes: ['card', 'p-4'],
      component_hint: 'features/mobile/MobileSessionHub',
      user_prompt: 'Adjust spacing to p-5 and align dark contrast',
      preset_tags: ['spacing', 'dark_mode'],
      computed_style_summary: {
        padding: '16px',
        backgroundColor: 'rgb(0, 0, 0)',
      },
    };

    const mockResponse: SelfEvolutionTaskResponse = {
      task_id: 'evo-12345678',
      status: 'verified',
      dom_selector: mockRequest.dom_selector,
      tag_name: mockRequest.tag_name,
      component_hint: mockRequest.component_hint,
      user_prompt: mockRequest.user_prompt,
      target_component_file: 'src/components/features/mobile/MobileSessionHub.tsx',
      diff_summary: '+ // evolution diff',
      recoverable_checkpoint_id: 'chk-87654321',
      created_at: '2026-10-12T06:00:00Z',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

    const result = await createSelfEvolutionTask(mockRequest);

    expect(apiClient.post).toHaveBeenCalledWith(
      '/self-evolution/tasks',
      mockRequest,
    );
    expect(result).toEqual(mockResponse);
  });

  it('listSelfEvolutionTasks fetches task list from /self-evolution/tasks', async () => {
    const mockList: SelfEvolutionTaskResponse[] = [
      {
        task_id: 'evo-aaa',
        status: 'verified',
        dom_selector: '.hero-btn',
        tag_name: 'button',
        user_prompt: 'Make button primary accent',
        recoverable_checkpoint_id: 'chk-aaa',
        created_at: '2026-10-12T06:00:00Z',
      },
    ];

    vi.mocked(apiClient.get).mockResolvedValueOnce(mockList);

    const result = await listSelfEvolutionTasks();

    expect(apiClient.get).toHaveBeenCalledWith('/self-evolution/tasks');
    expect(result).toEqual(mockList);
    expect(result).toHaveLength(1);
  });

  it('recoverSelfEvolution sends rollback request to /self-evolution/recover', async () => {
    const mockRecoverRes: SelfEvolutionRecoverResponse = {
      success: true,
      message: 'Successfully rolled back to safe checkpoint chk-aaa',
      restored_checkpoint_id: 'chk-aaa',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce(mockRecoverRes);

    const result = await recoverSelfEvolution({ checkpoint_id: 'chk-aaa' });

    expect(apiClient.post).toHaveBeenCalledWith('/self-evolution/recover', {
      checkpoint_id: 'chk-aaa',
    });
    expect(result).toEqual(mockRecoverRes);
    expect(result.success).toBe(true);
  });
});
