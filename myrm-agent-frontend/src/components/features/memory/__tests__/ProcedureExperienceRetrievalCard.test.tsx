/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/procedureExperience::listProcedures, registerProcedure, retrieveDualNode, splitIntents
 * ../command-center/ProcedureExperienceRetrievalCard::ProcedureExperienceRetrievalCard
 *
 * [OUTPUT]
 * Test suite verifying 8-field procedure protocol inspection, fixed-count dual-node retrieval,
 * and split-over-merge multi-intent decomposition.
 *
 * [POS]
 * Unit test for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProcedureExperienceRetrievalCard } from '../command-center/ProcedureExperienceRetrievalCard';
import type {
  DualNodeRetrievalResponseDTO,
  ProcedureMemoryEntryDTO,
} from '@/services/memory/procedureExperience';

const {
  mockListProcedures,
  mockRegisterProcedure,
  mockRetrieveDualNode,
  mockSplitIntents,
} = vi.hoisted(() => ({
  mockListProcedures: vi.fn(),
  mockRegisterProcedure: vi.fn(),
  mockRetrieveDualNode: vi.fn(),
  mockSplitIntents: vi.fn(),
}));

vi.mock('@/services/memory/procedureExperience', () => ({
  listProcedures: mockListProcedures,
  registerProcedure: mockRegisterProcedure,
  retrieveDualNode: mockRetrieveDualNode,
  splitIntents: mockSplitIntents,
}));

describe('ProcedureExperienceRetrievalCard', () => {
  const sampleEntries: ProcedureMemoryEntryDTO[] = [
    {
      entry_id: 'proc_deploy_ci_01',
      name: '生产发布门禁流水线规范',
      retrieval_anchor: 'intent:deploy-ci-pipeline|pre:lint-clean,vitest-pass|app:production,release',
      operation_intent: '在将代码发布或合并至主分支前，执行严格的代码质量与无障碍门禁检查',
      preconditions: ['工作区无破坏性未暂存代码', '全量单测通过'],
      immutable_boundary: ['禁止直接使用 git push -f 覆盖主分支', '禁止跳过 a11y ratchet 门禁'],
      procedure_steps: [
        '1. 执行 bun run lint 并确保 0 errors',
        '2. 执行 check-a11y-ratchet.mjs 校验 0 违规',
      ],
      write_field_provenance: { gate_status: '解析 vitest 与 ruff 退出状态码' },
      anti_patterns: ['绝不使用 any 类型注解', '绝不在修复 lint 时静默删除逻辑'],
      applicability: ['代码提交前的 pre-commit 审查', '生产部署工作流'],
      negative_applicability: ['本地临时探索原型阶段'],
      confidence: 1.0,
      created_at: '2026-10-08T04:00:00Z',
    },
    {
      entry_id: 'proc_data_isolation_02',
      name: '写前租户隔离与防越权校验',
      retrieval_anchor: 'intent:write-isolation-check|pre:session-scope-valid|app:database,mutation',
      operation_intent: '在执行持久化数据写操作前，强制执行作用域范围与租户隔离物理边界校验',
      preconditions: ['拥有明确的当前会话 session_id 或工作区作用域'],
      immutable_boundary: ['禁止跨作用域污染全局未授权资产'],
      procedure_steps: ['1. 提取当前调用上下文的 scope 与 session 标识', '2. 校验写入目标数据表'],
      write_field_provenance: { audit_fingerprint: '由时间戳与操作数据 SHA256 摘要派生' },
      anti_patterns: ['在没有 scope 过滤条件的情况下执行盲目批量更新'],
      applicability: ['所有涉及数据库 INSERT/UPDATE/DELETE 的写操作前'],
      negative_applicability: ['纯内存态临时只读计算'],
      confidence: 1.0,
      created_at: '2026-10-08T04:10:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockListProcedures.mockResolvedValue(sampleEntries);
  });

  it('renders the card header and 4-dimension HUD status metrics', async () => {
    render(<ProcedureExperienceRetrievalCard />);

    await waitFor(() => {
      expect(screen.getByText('过程形态经验协议与固定条数双节点检索')).toBeInTheDocument();
      expect(screen.getByText('Item 104 · P0')).toBeInTheDocument();
      expect(screen.getByText('八字段过程经验')).toBeInTheDocument();
      expect(screen.getByText('双节点精准拦截')).toBeInTheDocument();
      expect(screen.getByText('固定条数注入')).toBeInTheDocument();
      expect(screen.getByText('意图治理模式')).toBeInTheDocument();
    });

    expect(screen.getByText('八字段过程协议规范')).toBeInTheDocument();
    expect(screen.getByText('双节点固定条数检索')).toBeInTheDocument();
  });

  it('renders 8-field procedure items with preconditions, boundaries and anchors', async () => {
    render(<ProcedureExperienceRetrievalCard />);

    await waitFor(() => {
      expect(screen.getByText('生产发布门禁流水线规范')).toBeInTheDocument();
      expect(screen.getByText('写前租户隔离与防越权校验')).toBeInTheDocument();
      expect(screen.getAllByText('八字段完整合规').length).toBeGreaterThan(0);
      expect(screen.getByText(/intent:deploy-ci-pipeline/)).toBeInTheDocument();
      expect(screen.getByText(/禁止直接使用 git push -f 覆盖主分支/)).toBeInTheDocument();
      expect(screen.getByText(/绝不使用 any 类型注解/)).toBeInTheDocument();
    });
  });

  it('switches to dual-node console tab and executes fixed-count retrieval', async () => {
    const retrievalMockResult: DualNodeRetrievalResponseDTO = {
      node_kind: 'first_user',
      top_n_requested: 2,
      total_matched: 1,
      matched_entries: [sampleEntries[0]],
    };
    mockRetrieveDualNode.mockResolvedValue(retrievalMockResult);

    render(<ProcedureExperienceRetrievalCard />);

    await waitFor(() => {
      expect(screen.getByText('双节点固定条数检索')).toBeInTheDocument();
    });

    const consoleTab = screen.getByRole('button', { name: '切换到双节点固定条数检索控制台' });
    fireEvent.click(consoleTab);

    await waitFor(() => {
      expect(screen.getByText('固定条数双节点检索控制台 (Fixed-Count Dual-Node Retrieval)')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '执行双节点检索' })).toBeInTheDocument();
    });

    const retrieveBtn = screen.getByRole('button', { name: '执行双节点检索' });
    fireEvent.click(retrieveBtn);

    await waitFor(() => {
      expect(mockRetrieveDualNode).toHaveBeenCalledWith(
        expect.objectContaining({
          node_kind: 'first_user',
          top_n: 2,
        })
      );
      expect(screen.getByText(/检索命中结果/)).toBeInTheDocument();
      expect(screen.getByText(/固定条数注入保证 · 零字符预算折损/)).toBeInTheDocument();
    });
  });

  it('handles quick preset selection in dual-node console', async () => {
    const retrievalMockResult: DualNodeRetrievalResponseDTO = {
      node_kind: 'pre_write',
      top_n_requested: 1,
      total_matched: 1,
      matched_entries: [sampleEntries[1]],
    };
    mockRetrieveDualNode.mockResolvedValue(retrievalMockResult);

    render(<ProcedureExperienceRetrievalCard />);

    const consoleTab = screen.getByRole('button', { name: '切换到双节点固定条数检索控制台' });
    fireEvent.click(consoleTab);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '预设: 数据库写前隔离 (写前)' })).toBeInTheDocument();
    });

    const presetBtn = screen.getByRole('button', { name: '预设: 数据库写前隔离 (写前)' });
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(mockRetrieveDualNode).toHaveBeenCalledWith(
        expect.objectContaining({
          node_kind: 'pre_write',
          top_n: 1,
        })
      );
    });
  });

  it('runs multi-intent decomposition in split-over-merge tool', async () => {
    mockSplitIntents.mockResolvedValue({
      fragment_count: 2,
      fragments: [
        { intent: '意图 1 (更新依赖)', body: '运行 bun outdated 并更新' },
        { intent: '意图 2 (构建镜像)', body: '运行 bun run build' },
      ],
    });

    render(<ProcedureExperienceRetrievalCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /多意图.*拆条/ })).toBeInTheDocument();
    });

    const splitToggle = screen.getByRole('button', { name: /多意图.*拆条/ });
    fireEvent.click(splitToggle);

    await waitFor(() => {
      expect(screen.getByText('多意图强制拆解引擎 (Split-over-Merge)')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '执行强制拆解' })).toBeInTheDocument();
    });

    const runSplitBtn = screen.getByRole('button', { name: '执行强制拆解' });
    fireEvent.click(runSplitBtn);

    await waitFor(() => {
      expect(mockSplitIntents).toHaveBeenCalled();
      expect(screen.getByText('拆解生成 2 个独立意图片段:')).toBeInTheDocument();
      expect(screen.getByText('意图 1 (更新依赖)')).toBeInTheDocument();
      expect(screen.getByText('意图 2 (构建镜像)')).toBeInTheDocument();
    });
  });
});
