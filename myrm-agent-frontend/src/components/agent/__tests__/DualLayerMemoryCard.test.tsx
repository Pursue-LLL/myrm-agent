'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DualLayerMemoryCard } from '../DualLayerMemoryCard';

const intl = vi.hoisted(() => ({ locale: 'zh' as 'en' | 'zh' }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

const { mockGetProfileNotesContents, mockUpdateProfileNotesContents, mockCheckProfileNotesIntake } = vi.hoisted(() => ({
  mockGetProfileNotesContents: vi.fn(),
  mockUpdateProfileNotesContents: vi.fn(),
  mockCheckProfileNotesIntake: vi.fn(),
}));

vi.mock('@/services/memory/profileNotes', () => ({
  getProfileNotesContents: mockGetProfileNotesContents,
  updateProfileNotesContents: mockUpdateProfileNotesContents,
  checkProfileNotesIntake: mockCheckProfileNotesIntake,
}));

describe('DualLayerMemoryCard', () => {
  const initialContent = {
    user_content: '用户偏好使用 Python PEP8 规范',
    memory_content: '框架与业务分层架构，禁止反向依赖',
    user_watermark: {
      layer: 'user',
      current_chars: 20,
      max_chars: 1375,
      usage_ratio: 0.0145,
      level: 'safe' as const,
      warning_message: null,
    },
    memory_watermark: {
      layer: 'memory',
      current_chars: 20,
      max_chars: 2200,
      usage_ratio: 0.009,
      level: 'safe' as const,
      warning_message: null,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    intl.locale = 'zh';
    mockGetProfileNotesContents.mockResolvedValue(initialContent);
    mockUpdateProfileNotesContents.mockResolvedValue(initialContent);
  });

  it('renders dual layer titles, budgets, and textareas', async () => {
    render(<DualLayerMemoryCard />);

    await waitFor(() => {
      expect(screen.getByText('双层画像与智能体笔记看板')).toBeDefined();
    });

    expect(screen.getByText('用户长期偏好')).toBeDefined();
    expect(screen.getByText('智能体专属笔记')).toBeDefined();
    expect(screen.getByDisplayValue('用户偏好使用 Python PEP8 规范')).toBeDefined();
    expect(screen.getByDisplayValue('框架与业务分层架构，禁止反向依赖')).toBeDefined();
  });

  it('triggers save action and updates state', async () => {
    const onSaved = vi.fn();
    mockUpdateProfileNotesContents.mockResolvedValueOnce({
      ...initialContent,
      user_content: '用户偏好使用 Python PEP8 规范，严禁 Any',
    });

    render(<DualLayerMemoryCard onSaved={onSaved} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('用户偏好使用 Python PEP8 规范')).toBeDefined();
    });

    const saveBtn = screen.getByRole('button', { name: /保存记忆/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdateProfileNotesContents).toHaveBeenCalledTimes(1);
      expect(onSaved).toHaveBeenCalledTimes(1);
      expect(screen.getByText('双层记忆已成功同步保存。')).toBeDefined();
    });
  });

  it('evaluates intake noise tester correctly on rejection', async () => {
    mockCheckProfileNotesIntake.mockResolvedValueOnce({
      accepted: false,
      target_layer: null,
      rejected_reason: 'Rejected task progress milestone: matched phase 2 completed.',
      garbage_category: 'TASK_PROGRESS',
    });

    render(<DualLayerMemoryCard />);

    const input = screen.getByPlaceholderText(/输入候选记忆/i);
    fireEvent.change(input, { target: { value: 'Phase 2 completed and verified' } });

    const probeBtn = screen.getByRole('button', { name: /检测准入/i });
    fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(mockCheckProfileNotesIntake).toHaveBeenCalledWith({
        content: 'Phase 2 completed and verified',
      });
      expect(screen.getByText(/准入拒绝：判定为短期瞬态垃圾 \[TASK_PROGRESS\]/)).toBeDefined();
      expect(screen.getByText(/Rejected task progress milestone/i)).toBeDefined();
    });
  });

  it('evaluates intake noise tester correctly on acceptance', async () => {
    mockCheckProfileNotesIntake.mockResolvedValueOnce({
      accepted: true,
      target_layer: 'user',
      rejected_reason: null,
      garbage_category: null,
    });

    render(<DualLayerMemoryCard />);

    const input = screen.getByPlaceholderText(/输入候选记忆/i);
    fireEvent.change(input, { target: { value: '偏好深色模式' } });

    const probeBtn = screen.getByRole('button', { name: /检测准入/i });
    fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(mockCheckProfileNotesIntake).toHaveBeenCalledWith({
        content: '偏好深色模式',
      });
      expect(screen.getByText(/准入放行：路由至 USER 层/)).toBeDefined();
    });
  });

  it('shows the same card in English when the locale is English', async () => {
    intl.locale = 'en';
    render(<DualLayerMemoryCard />);

    await waitFor(() => {
      expect(screen.getByText('User profile and agent notes (dual-layer memory)')).toBeDefined();
    });

    expect(screen.getByText('User profile')).toBeDefined();
    expect(screen.getByText('Agent notes')).toBeDefined();
    expect(screen.getByRole('button', { name: /Save memory/ })).toBeDefined();
    expect(screen.getAllByText('Normal').length).toBe(2);
  });

  it('reports a failed load in the user language', async () => {
    mockGetProfileNotesContents.mockRejectedValueOnce(new Error('offline'));
    render(<DualLayerMemoryCard />);

    await waitFor(() => {
      expect(screen.getByText('加载双层记忆失败，请检查网络或后端状态。')).toBeDefined();
    });
  });
});
