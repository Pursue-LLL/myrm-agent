/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TaskTriadTrajectoryCard } from '../command-center/TaskTriadTrajectoryCard';
import type {
  AntiLoopSnapshotResponseDTO,
  CheckActionResponseDTO,
  TaskTrajectoryBlackboxResponseDTO,
} from '@/services/memory/taskTriadTrajectory';

const {
  mockGetTaskBlackbox,
  mockCheckActionProhibited,
  mockGetAntiLoopSnapshot,
  mockRecordMilestone,
  mockRecordFailedAttempt,
  mockRecordUserSteering,
} = vi.hoisted(() => ({
  mockGetTaskBlackbox: vi.fn(),
  mockCheckActionProhibited: vi.fn(),
  mockGetAntiLoopSnapshot: vi.fn(),
  mockRecordMilestone: vi.fn(),
  mockRecordFailedAttempt: vi.fn(),
  mockRecordUserSteering: vi.fn(),
}));

vi.mock('@/services/memory/taskTriadTrajectory', () => ({
  getTaskBlackbox: mockGetTaskBlackbox,
  checkActionProhibited: mockCheckActionProhibited,
  getAntiLoopSnapshot: mockGetAntiLoopSnapshot,
  recordMilestone: mockRecordMilestone,
  recordFailedAttempt: mockRecordFailedAttempt,
  recordUserSteering: mockRecordUserSteering,
}));

describe('TaskTriadTrajectoryCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockBlackboxData: TaskTrajectoryBlackboxResponseDTO = {
    task_id: 'task_refactor_jwt_01',
    session_id: 'session_dev_main',
    initial_goal: '长程超长任务：重构系统认证模块为无状态架构',
    status: 'running',
    version: 4,
    milestones: [
      {
        milestone_id: 'ms_01',
        step_index: 2,
        title: '密码哈希升级为 Argon2id',
        description: '已跑通单元测试',
        verified_output_summary: '12 项密码学单测全绿，耗时 120ms',
        artifacts_produced: ['src/auth/hash.ts'],
        timestamp: '2026-10-08T02:00:00Z',
      },
    ],
    failed_attempts: [
      {
        attempt_id: 'fa_01',
        step_index: 4,
        action_attempted: 'docker run -p 8080:8080 auth-service',
        error_type: 'PortConflict',
        error_summary: '端口 8080 被占用导致容器起不来',
        dead_end_pattern: '8080:8080',
        prohibited_rule: '严禁再绑定 8080 端口，必须使用 8081 或动态端口',
        lessons_learned: '先执行 lsof 检查端口占用',
        timestamp: '2026-10-08T02:10:00Z',
      },
    ],
    user_steerings: [
      {
        steering_id: 'st_01',
        turn_index: 3,
        instruction_raw: '不要引入 Redis，全部使用本地无依赖内存缓存！',
        distilled_constraint: '严禁引入 Redis 依赖，必须使用内存缓存',
        scope: 'global',
        is_active: true,
        timestamp: '2026-10-08T02:05:00Z',
      },
    ],
    created_at: '2026-10-08T01:50:00Z',
    updated_at: '2026-10-08T02:15:00Z',
  };

  const mockBlockedCheckResult: CheckActionResponseDTO = {
    is_prohibited: true,
    matched_rule: '严禁再绑定 8080 端口，必须使用 8081 或动态端口',
    error_summary: '端口 8080 被占用导致容器起不来',
    matched_pattern: '8080:8080',
  };

  const mockSafeCheckResult: CheckActionResponseDTO = {
    is_prohibited: false,
    matched_rule: null,
    error_summary: null,
    matched_pattern: null,
  };

  const mockSnapshotResult: AntiLoopSnapshotResponseDTO = {
    task_id: 'task_refactor_jwt_01',
    snapshot_token_estimate: 95,
    dead_end_rules_injected: ['禁试: 8080:8080 (根因: 端口 8080 被占用)'],
    active_user_steerings_injected: ['约束: 严禁引入 Redis 依赖'],
    latest_milestone_title: '密码哈希升级为 Argon2id',
    formatted_prompt_block:
      '<task_triad_blackbox task_id="task_refactor_jwt_01">\n【最新在途用户约束】: 严禁引入 Redis 依赖\n【已试死胡同禁令】: 禁试 8080:8080\n【已验证里程碑】: 密码哈希升级为 Argon2id\n</task_triad_blackbox>',
  };

  it('renders initial triad state and displays HUD counters and details', async () => {
    mockGetTaskBlackbox.mockResolvedValueOnce(mockBlackboxData);

    render(<TaskTriadTrajectoryCard />);

    expect(screen.getByTestId('task-triad-trajectory-card')).toBeInTheDocument();
    expect(screen.getByText(/超长任务三元状态轨迹黑匣子/)).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetTaskBlackbox).toHaveBeenCalledWith('task_refactor_jwt_01');
    });

    expect(await screen.findByText(/密码哈希升级为 Argon2id/)).toBeInTheDocument();
    expect(screen.getByText(/严禁再绑定 8080 端口/)).toBeInTheDocument();
    expect(screen.getByText(/严禁引入 Redis 依赖，必须使用内存缓存/)).toBeInTheDocument();
  });

  it('checks action against dead-end patterns and displays blocked warning', async () => {
    mockGetTaskBlackbox.mockResolvedValueOnce(mockBlackboxData);
    mockCheckActionProhibited.mockResolvedValueOnce(mockBlockedCheckResult);

    render(<TaskTriadTrajectoryCard />);

    const checkBtn = screen.getByRole('button', { name: /防循环预检/ });
    fireEvent.click(checkBtn);

    expect(await screen.findByText(/命中死胡同禁令，已硬阻断/)).toBeInTheDocument();
    expect(screen.getAllByText(/严禁再绑定 8080 端口/)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/端口 8080 被占用导致容器起不来/)[0]).toBeInTheDocument();
  });

  it('checks safe action and displays safety confirmation', async () => {
    mockGetTaskBlackbox.mockResolvedValueOnce(mockBlackboxData);
    mockCheckActionProhibited.mockResolvedValueOnce(mockSafeCheckResult);

    render(<TaskTriadTrajectoryCard />);

    const input = screen.getByLabelText(/单步动作死胡同拦截雷达/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'bun test tests/unit/auth.test.ts' } });

    const checkBtn = screen.getByRole('button', { name: /防循环预检/ });
    fireEvent.click(checkBtn);

    expect(await screen.findByText(/动作安全，未触碰已知死胡同/)).toBeInTheDocument();
  });

  it('generates and displays pre-prompt anti-loop snapshot', async () => {
    mockGetTaskBlackbox.mockResolvedValueOnce(mockBlackboxData);
    mockGetAntiLoopSnapshot.mockResolvedValueOnce(mockSnapshotResult);

    render(<TaskTriadTrajectoryCard />);

    const snapshotBtn = screen.getByRole('button', { name: /生成注入快照/ });
    fireEvent.click(snapshotBtn);

    expect(await screen.findByText(/预估 Token 占用:/)).toBeInTheDocument();
    expect(screen.getByText('95')).toBeInTheDocument();
    expect(screen.getByText(/<task_triad_blackbox/)).toBeInTheDocument();
  });

  it('applies quick test presets and invokes corresponding API endpoints', async () => {
    mockGetTaskBlackbox.mockResolvedValue(mockBlackboxData);
    mockRecordMilestone.mockResolvedValueOnce({});
    mockRecordFailedAttempt.mockResolvedValueOnce({});
    mockRecordUserSteering.mockResolvedValueOnce({});

    render(<TaskTriadTrajectoryCard />);

    // 1. Milestone preset
    const msPresetBtn = screen.getByRole('button', { name: /达成新里程碑/ });
    fireEvent.click(msPresetBtn);

    await waitFor(() => {
      expect(mockRecordMilestone).toHaveBeenCalled();
    });

    // 2. Dead-end preset
    const dePresetBtn = screen.getByRole('button', { name: /记录死胡同避坑/ });
    fireEvent.click(dePresetBtn);

    await waitFor(() => {
      expect(mockRecordFailedAttempt).toHaveBeenCalled();
    });

    // 3. Steering preset
    const stPresetBtn = screen.getByRole('button', { name: /追加在途约束/ });
    fireEvent.click(stPresetBtn);

    await waitFor(() => {
      expect(mockRecordUserSteering).toHaveBeenCalled();
    });
  });

  it('falls back gracefully when blackbox API request fails', async () => {
    mockGetTaskBlackbox.mockRejectedValueOnce(new Error('Network offline'));

    render(<TaskTriadTrajectoryCard />);

    expect(await screen.findByText(/密码哈希升级为 Argon2id/)).toBeInTheDocument();
    expect(screen.getAllByText(/严禁再绑定 8080 端口/)[0]).toBeInTheDocument();
  });
});
