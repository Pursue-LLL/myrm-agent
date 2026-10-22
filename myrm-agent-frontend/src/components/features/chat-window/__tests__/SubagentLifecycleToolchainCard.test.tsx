import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  SubagentLifecycleToolchainCard,
  SubagentTaskItemData,
} from '../SubagentLifecycleToolchainCard';

describe('SubagentLifecycleToolchainCard', () => {
  const mockTasks: SubagentTaskItemData[] = [
    {
      subagent_id: 'subagent-test-01',
      parent_session_id: 'chat-test-01',
      task_prompt: '审计用户权限模块的安全隐患',
      agent_profile: 'security_auditor',
      tools_whitelist: ['read_file'],
      status: 'running',
      timeout_seconds: 60.0,
      created_at: '2026-10-15T12:00:00Z',
      started_at: '2026-10-15T12:00:01Z',
      token_usage: 450,
      step_count: 2,
      input_queue: [],
      events: [
        {
          event_id: 'evt-1',
          event_type: 'SUBAGENT_SPAWNED',
          subagent_id: 'subagent-test-01',
          payload: {},
          timestamp: '2026-10-15T12:00:01Z',
        },
      ],
    },
    {
      subagent_id: 'subagent-test-02',
      parent_session_id: 'chat-test-01',
      task_prompt: '提取数据库 Schema 蓝图',
      agent_profile: 'db_scout',
      tools_whitelist: ['read_file'],
      status: 'completed',
      timeout_seconds: 60.0,
      created_at: '2026-10-15T12:00:00Z',
      started_at: '2026-10-15T12:00:01Z',
      ended_at: '2026-10-15T12:00:05Z',
      result_summary: 'Schema 结构分析完成',
      token_usage: 1200,
      step_count: 4,
      input_queue: [],
      events: [],
    },
  ];

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/subagents/spawn')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                subagent_id: 'subagent-new-99',
                parent_session_id: 'chat-test-01',
                task_prompt: '测试派发新子任务',
                agent_profile: 'general_worker',
                tools_whitelist: ['read_file'],
                status: 'running',
                timeout_seconds: 60.0,
                created_at: '2026-10-15T12:01:00Z',
                token_usage: 0,
                step_count: 0,
                input_queue: [],
                events: [],
              },
            }),
          });
        }
        if (url.includes('/input')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                message_id: 'msg-1',
                subagent_id: 'subagent-test-01',
                content: '指令内容',
                sender_role: 'orchestrator',
                created_at: '2026-10-15T12:01:30Z',
              },
            }),
          });
        }
        if (url.includes('/kill')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockTasks[0],
                status: 'killed',
                kill_reason: '用户手动硬熔断',
              },
            }),
          });
        }
        if (url.includes('/subagents/wait')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                all_completed: true,
                completed_count: 1,
                failed_count: 0,
                killed_count: 1,
                timeout_count: 0,
                tasks: mockTasks,
              },
            }),
          });
        }
        if (url.includes('/subagents')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                tasks: mockTasks,
                total: mockTasks.length,
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

  it('renders card with initial tasks and handles dismiss', async () => {
    const handleDismiss = vi.fn();

    await act(async () => {
      render(
        <SubagentLifecycleToolchainCard
          chatId="chat-test-01"
          initialTasks={mockTasks}
          onDismiss={handleDismiss}
        />,
      );
    });

    expect(screen.getByText('原生 Subagent 细粒度生命周期管控')).toBeInTheDocument();
    expect(screen.getByText('subagent-test-01')).toBeInTheDocument();
    expect(screen.getByText('security_auditor')).toBeInTheDocument();
    expect(screen.getByText('subagent-test-02')).toBeInTheDocument();
    expect(screen.getByText('审计用户权限模块的安全隐患')).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('spawns a new subagent when button is clicked', async () => {
    await act(async () => {
      render(
        <SubagentLifecycleToolchainCard
          chatId="chat-test-01"
          initialTasks={mockTasks}
        />,
      );
    });

    const promptInput = screen.getByPlaceholderText('输入任务指令以按需 spawn 子智能体...');
    fireEvent.change(promptInput, { target: { value: '测试派发新子任务' } });

    const spawnBtn = screen.getByRole('button', { name: /Spawn/ });
    await act(async () => {
      fireEvent.click(spawnBtn);
    });

    expect(screen.getByText('subagent-new-99')).toBeInTheDocument();
  });

  it('sends input guidance to running subagent', async () => {
    await act(async () => {
      render(
        <SubagentLifecycleToolchainCard
          chatId="chat-test-01"
          initialTasks={mockTasks}
        />,
      );
    });

    const steerInput = screen.getByPlaceholderText('动态注入纠偏指令...');
    fireEvent.change(steerInput, { target: { value: '请优先检查 JWT 逻辑' } });

    // The send button is in the running subagent's control bar
    const buttons = screen.getAllByRole('button');
    const sendButton = buttons.find((b) => b.querySelector('svg.lucide-send'));
    expect(sendButton).toBeDefined();

    if (sendButton) {
      await act(async () => {
        fireEvent.click(sendButton);
      });
      expect(screen.getByText(/已向 subagent-test-01 注入指导/)).toBeInTheDocument();
    }
  });

  it('kills running subagent on button click', async () => {
    await act(async () => {
      render(
        <SubagentLifecycleToolchainCard
          chatId="chat-test-01"
          initialTasks={mockTasks}
        />,
      );
    });

    const killBtn = screen.getByRole('button', { name: /Kill/ });
    await act(async () => {
      fireEvent.click(killBtn);
    });

    expect(screen.getByText(/已被熔断终止/)).toBeInTheDocument();
  });

  it('waits for all subagents on button click', async () => {
    await act(async () => {
      render(
        <SubagentLifecycleToolchainCard
          chatId="chat-test-01"
          initialTasks={mockTasks}
        />,
      );
    });

    const waitBtn = screen.getByRole('button', { name: /Wait All 批量汇聚/ });
    await act(async () => {
      fireEvent.click(waitBtn);
    });

    expect(screen.getByText(/批量汇聚完成/)).toBeInTheDocument();
  });
});
