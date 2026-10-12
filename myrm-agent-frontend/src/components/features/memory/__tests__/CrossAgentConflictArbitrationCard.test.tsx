/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CrossAgentConflictArbitrationCard } from '../command-center/CrossAgentConflictArbitrationCard';
import type {
  ArbitrationOutcomeDTO,
  ComposableContextResponseDTO,
  HandoffPacketDTO,
  HandoffVerificationResponseDTO,
} from '@/services/memory/crossAgent';

const {
  mockArbitrateMemoryConflict,
  mockProjectComposableContext,
  mockSealTaskHandoff,
  mockVerifyTaskHandoff,
} = vi.hoisted(() => ({
  mockArbitrateMemoryConflict: vi.fn(),
  mockProjectComposableContext: vi.fn(),
  mockSealTaskHandoff: vi.fn(),
  mockVerifyTaskHandoff: vi.fn(),
}));

vi.mock('@/services/memory/crossAgent', () => ({
  arbitrateMemoryConflict: mockArbitrateMemoryConflict,
  projectComposableContext: mockProjectComposableContext,
  sealTaskHandoff: mockSealTaskHandoff,
  verifyTaskHandoff: mockVerifyTaskHandoff,
}));

describe('CrossAgentConflictArbitrationCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockResolvedOutcome: ArbitrationOutcomeDTO = {
    divergence_id: 'div-test-01',
    resolved: true,
    policy_applied: 'ground_truth_first',
    winning_assertion: {
      assertion_id: 'ast-coder',
      subject: 'database_backend',
      predicate: 'uses',
      object_value: 'sqlite',
      confidence: 0.9,
      source_agent_id: 'coder_agent',
      source_reference: 'config.py',
    },
    audit_rationale: 'Physical ground truth confirmed in config.py.',
    requires_human_confirmation: false,
  };

  const mockHumanConfirmationOutcome: ArbitrationOutcomeDTO = {
    divergence_id: 'div-test-02',
    resolved: false,
    policy_applied: 'human_in_the_loop',
    winning_assertion: {
      assertion_id: 'ast-coder',
      subject: 'database_backend',
      predicate: 'uses',
      object_value: 'sqlite',
      confidence: 0.9,
      source_agent_id: 'coder_agent',
    },
    audit_rationale: 'Symmetric deadlock between agents. Suspended pending human confirmation.',
    requires_human_confirmation: true,
  };

  const mockProjectionResponse: ComposableContextResponseDTO = {
    agent_id: 'subagent_worker_1',
    session_id: 'session_coord_99',
    total_tokens: 380,
    layers: [
      {
        layer_kind: 'profile_tools',
        title: 'Agent Persona & Tool Capabilities',
        content: '- Role: Senior Full-Stack Engineer\n- Tools: pytest, ruff',
        token_count: 80,
        content_hash: 'hash-profile',
        is_shared: false,
      },
      {
        layer_kind: 'global_ground_truth',
        title: 'Global Project Ground Truth Facts',
        content: '- Database backend is SQLite',
        token_count: 60,
        content_hash: 'hash-global',
        is_shared: true,
      },
      {
        layer_kind: 'private_scratchpad',
        title: 'Private Scratchpad (Confidential to this Agent)',
        content: 'Private note: analyzing AST parsing performance',
        token_count: 90,
        content_hash: 'hash-scratchpad',
        is_shared: false,
      },
      {
        layer_kind: 'ephemeral_handoff',
        title: 'Ephemeral Task Handoff Packet',
        content: 'No pending task handoff.',
        token_count: 150,
        content_hash: 'hash-handoff',
        is_shared: false,
      },
    ],
    assembled_prompt_text: 'Assembled Context Prompt...',
    cache_prefix_hash: 'sha256-stabilized-prefix-hash-value-1234567890',
  };

  const mockHandoffPacket: HandoffPacketDTO = {
    packet_id: 'pkt-test-8888',
    source_agent_id: 'agent_planner',
    target_agent_id: 'agent_executor',
    task_id: 'task_refactor_module',
    context_snapshot: 'Refactored core mixins. All unit tests passed.',
    critical_assertions: [
      {
        assertion_id: 'ast-task-target',
        subject: 'task_target',
        predicate: 'is',
        object_value: 'refactor_completed',
        confidence: 1.0,
        source_agent_id: 'agent_planner',
      },
    ],
    timestamp: 1700000000.0,
    signature_sha256: 'deadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678',
  };

  const mockVerificationResult: HandoffVerificationResponseDTO = {
    packet_id: 'pkt-test-8888',
    is_valid: true,
    verified_assertions_count: 1,
    rejection_reason: null,
  };

  it('renders card header and default arbitration tab', () => {
    render(<CrossAgentConflictArbitrationCard />);
    expect(screen.getByText('跨智能体可组合上下文隔离与分歧仲裁套件')).toBeInTheDocument();
    expect(screen.getByText('Item 177 • P0 资产')).toBeInTheDocument();
    expect(screen.getByText('启动多模型分歧仲裁探针')).toBeInTheDocument();
  });

  it('triggers conflict arbitration and displays resolved report', async () => {
    mockArbitrateMemoryConflict.mockResolvedValueOnce(mockResolvedOutcome);
    render(<CrossAgentConflictArbitrationCard />);

    const arbitrateBtn = screen.getByRole('button', { name: /启动多模型分歧仲裁探针/i });
    fireEvent.click(arbitrateBtn);

    await waitFor(() => {
      expect(mockArbitrateMemoryConflict).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('仲裁探针报告')).toBeInTheDocument();
    expect(screen.getByText('分歧已确定性裁决')).toBeInTheDocument();
    expect(screen.getByText('ground_truth_first')).toBeInTheDocument();
  });

  it('handles human-in-the-loop escalation with 1-click confirmation', async () => {
    mockArbitrateMemoryConflict.mockResolvedValueOnce(mockHumanConfirmationOutcome);
    render(<CrossAgentConflictArbitrationCard />);

    fireEvent.click(screen.getByRole('button', { name: /启动多模型分歧仲裁探针/i }));

    await waitFor(() => {
      expect(screen.getByText('对称僵局，待人工终审')).toBeInTheDocument();
    });

    expect(screen.getByText(/需人工介入确认/i)).toBeInTheDocument();

    const confirmBtnA = screen.getByRole('button', { name: /确认采纳 Agent A/i });
    fireEvent.click(confirmBtnA);

    expect(screen.queryByText(/需人工介入确认/i)).not.toBeInTheDocument();
  });

  it('switches to projection tab and generates 4-layer context HUD', async () => {
    mockProjectComposableContext.mockResolvedValueOnce(mockProjectionResponse);
    render(<CrossAgentConflictArbitrationCard />);

    fireEvent.click(screen.getByRole('tab', { name: /4层可组合投影/i }));

    const projectBtn = screen.getByRole('button', { name: /组装可组合上下文投影/i });
    fireEvent.click(projectBtn);

    await waitFor(() => {
      expect(mockProjectComposableContext).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/4层可组合上下文投影 HUD/i)).toBeInTheDocument();
    expect(screen.getByText(/KV-Cache 命中预测: ~82%/i)).toBeInTheDocument();
    expect(screen.getByText(/sha256-stabilized-prefix-hash-value-1234567890/i)).toBeInTheDocument();
  });

  it('switches to handoff tab and seals/verifies packet', async () => {
    mockSealTaskHandoff.mockResolvedValueOnce(mockHandoffPacket);
    mockVerifyTaskHandoff.mockResolvedValueOnce(mockVerificationResult);

    render(<CrossAgentConflictArbitrationCard />);

    fireEvent.click(screen.getByRole('tab', { name: /任务移交验签/i }));

    const sealBtn = screen.getByRole('button', { name: /生成 SHA-256 移交封签/i });
    fireEvent.click(sealBtn);

    await waitFor(() => {
      expect(mockSealTaskHandoff).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('封签移交包详情')).toBeInTheDocument();

    const verifyBtn = screen.getByRole('button', { name: /验证移交包签名/i });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(mockVerifyTaskHandoff).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/验签通过：完整性完好/i)).toBeInTheDocument();
    expect(screen.getByText('SECURE')).toBeInTheDocument();
  });
});
