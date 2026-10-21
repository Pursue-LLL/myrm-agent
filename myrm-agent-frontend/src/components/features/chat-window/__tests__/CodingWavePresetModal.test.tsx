import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  CodingWavePresetModal,
  WaveProgressData,
  WavePresetConfigData,
} from '../CodingWavePresetModal';

describe('CodingWavePresetModal', () => {
  const mockPreset: WavePresetConfigData = {
    preset_id: 'preset-fullstack-wave-v1',
    name: '全栈开发波次流水线预置',
    description: 'Tech-Lead / Full-Stack Dev / QA Reviewer 波次编排',
    role_model_routing: {
      'tech-lead': 'kimi-k3',
      'fullstack-dev': 'ornith-1.5',
      'qa-reviewer': 'glm-5.3',
    },
  };

  const mockProgress: WaveProgressData = {
    session_id: 'wave-sess-100',
    current_stage: 'planning',
    tasks: [
      {
        task_id: 'task-plan-1',
        stage: 'planning',
        title: '架构设计与需求拆解',
        role: 'tech-lead',
        model_override: 'kimi-k3',
        status: 'completed',
        output_summary: '系统架构分解完成',
      },
      {
        task_id: 'task-dev-1',
        stage: 'wave1_dev',
        title: '核心数据层与业务逻辑编码',
        role: 'fullstack-dev',
        model_override: 'ornith-1.5',
        status: 'pending',
      },
    ],
    is_completed: false,
    updated_at: '2026-10-15T12:00:00Z',
  };

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/coding-wave/preset')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ data: mockPreset }),
          });
        }
        if (url.includes('/coding-wave/progress')) {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({ detail: 'Not found' }),
          });
        }
        if (url.includes('/coding-wave/sessions')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockProgress,
                session_id: 'wave-sess-new',
              },
            }),
          });
        }
        if (url.includes('/coding-wave/advance')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockProgress,
                current_stage: 'wave1_dev',
              },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ data: {} }),
        });
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders modal with initial progress and handles dismiss', async () => {
    const handleDismiss = vi.fn();

    await act(async () => {
      render(
        <CodingWavePresetModal
          chatId="chat-123"
          initialProgress={mockProgress}
          initialPreset={mockPreset}
          onDismiss={handleDismiss}
        />,
      );
    });

    expect(screen.getByText('全栈开发 Wave 波次编排')).toBeInTheDocument();
    expect(screen.getByText('当前阶段: PLANNING')).toBeInTheDocument();
    expect(screen.getByText('架构设计与需求拆解')).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches between tabs cleanly', async () => {
    await act(async () => {
      render(
        <CodingWavePresetModal
          chatId="chat-123"
          initialProgress={mockProgress}
          initialPreset={mockPreset}
        />,
      );
    });

    const routingTab = screen.getByRole('button', { name: '三模型角色分工' });
    fireEvent.click(routingTab);
    expect(screen.getByText('tech-lead')).toBeInTheDocument();
    expect(screen.getByText('kimi-k3')).toBeInTheDocument();

    const exportTab = screen.getByRole('button', { name: '进度工件' });
    fireEvent.click(exportTab);
    expect(screen.getByText('下载 orchestration_progress.json')).toBeInTheDocument();
  });

  it('initializes wave pipeline when button clicked', async () => {
    await act(async () => {
      render(
        <CodingWavePresetModal
          chatId="chat-456"
          initialProgress={null}
          initialPreset={mockPreset}
        />,
      );
    });

    const initBtn = screen.getByRole('button', { name: /一键启动开发流水线/ });
    await act(async () => {
      fireEvent.click(initBtn);
    });

    expect(screen.getByText('波次开发流水线已初始化')).toBeInTheDocument();
  });

  it('advances wave stage on button click', async () => {
    await act(async () => {
      render(
        <CodingWavePresetModal
          chatId="chat-789"
          initialProgress={mockProgress}
          initialPreset={mockPreset}
        />,
      );
    });

    const advanceBtn = screen.getByRole('button', { name: /门禁核验并推进下一阶段/ });
    await act(async () => {
      fireEvent.click(advanceBtn);
    });

    expect(screen.getByText('波次阶段已推进至: wave1_dev')).toBeInTheDocument();
  });
});
