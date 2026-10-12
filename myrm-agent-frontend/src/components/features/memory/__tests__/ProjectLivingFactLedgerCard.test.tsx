/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProjectLivingFactLedgerCard } from '../command-center/ProjectLivingFactLedgerCard';
import type {
  ContextProjectionResponseDTO,
  LivingFactDTO,
  LivingFactListResponseDTO,
  ValidationAuditResponseDTO,
} from '@/services/projects/projectState';

const {
  mockListLivingFacts,
  mockRecordLivingFact,
  mockDeleteLivingFact,
  mockProjectContext,
  mockAuditValidation,
} = vi.hoisted(() => ({
  mockListLivingFacts: vi.fn(),
  mockRecordLivingFact: vi.fn(),
  mockDeleteLivingFact: vi.fn(),
  mockProjectContext: vi.fn(),
  mockAuditValidation: vi.fn(),
}));

vi.mock('@/services/projects/projectState', () => ({
  listLivingFacts: mockListLivingFacts,
  recordLivingFact: mockRecordLivingFact,
  deleteLivingFact: mockDeleteLivingFact,
  projectContext: mockProjectContext,
  auditValidation: mockAuditValidation,
}));

describe('ProjectLivingFactLedgerCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockFactList: LivingFactDTO[] = [
    {
      fact_id: 'fact-dec-01',
      project_id: 'default-project',
      fact_type: 'decision',
      title: '采用单文件嵌入式 sqlite-vec 存储',
      content: '单机与本地桌面端采用 sqlite-vec 零守护进程引擎。',
      target_components: ['memory', 'storage'],
      reason_or_constraint: '轻量化开箱即用',
      validation_count: 3,
      regression_count: 0,
      promotion_stage: 'knowledge',
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-06T12:00:00Z',
      metadata: {},
    },
    {
      fact_id: 'fact-rej-01',
      project_id: 'default-project',
      fact_type: 'rejected_alternative',
      title: '否决 Milvus 外部独立容器',
      content: '否决强制外部独立 Docker 容器向量数据库方案。',
      target_components: ['storage'],
      reason_or_constraint: '内存占用过大',
      validation_count: 1,
      regression_count: 0,
      promotion_stage: 'confirmed_fact',
      created_at: '2026-10-02T11:00:00Z',
      updated_at: '2026-10-05T14:00:00Z',
      metadata: {},
    },
    {
      fact_id: 'fact-con-01',
      project_id: 'default-project',
      fact_type: 'constraint',
      title: '单文件行数不超过 400 行',
      content: '单个源文件严格控制在 400 行以内。',
      target_components: ['code_quality'],
      reason_or_constraint: '极高可维护性',
      validation_count: 5,
      regression_count: 0,
      promotion_stage: 'skill',
      created_at: '2026-10-01T08:00:00Z',
      updated_at: '2026-10-07T16:00:00Z',
      metadata: {},
    },
  ];

  const mockListResponse: LivingFactListResponseDTO = {
    project_id: 'default-project',
    total_count: 3,
    facts: mockFactList,
  };

  const mockProjectionResponse: ContextProjectionResponseDTO = {
    project_id: 'default-project',
    rule_layer_facts: [mockFactList[2]],
    dependency_layer_facts: [mockFactList[0]],
    semantic_layer_facts: [mockFactList[1]],
    routed_facts: mockFactList,
    token_count_estimated: 380,
    token_budget: 1500,
    projected_context_prompt: '[PROJECT_STATE: default-project]\n- CONSTRAINT: 单文件行数限制\n- DECISION: sqlite-vec',
  };

  const mockAuditResponse: ValidationAuditResponseDTO = {
    fact_id: 'fact-dec-01',
    project_id: 'default-project',
    passed: true,
    previous_stage: 'confirmed_fact',
    current_stage: 'knowledge',
    promotion_occurred: true,
    regression_occurred: false,
    validation_count: 4,
    regression_count: 0,
    message: '经验成功晋升至 knowledge 阶段',
  };

  it('renders initial state and displays living facts', async () => {
    mockListLivingFacts.mockResolvedValueOnce(mockListResponse);

    render(<ProjectLivingFactLedgerCard />);

    expect(
      screen.getByText(/项目事实账本与四层上下文投影/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Item 63 · P0')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockListLivingFacts).toHaveBeenCalledWith('default-project');
    });

    expect(screen.getByText('采用单文件嵌入式 sqlite-vec 存储')).toBeInTheDocument();
    expect(screen.getByText('否决 Milvus 外部独立容器')).toBeInTheDocument();
    expect(screen.getByText('单文件行数不超过 400 行')).toBeInTheDocument();
    expect(screen.getByText('knowledge')).toBeInTheDocument();
    expect(screen.getByText('skill')).toBeInTheDocument();
  });

  it('supports filtering facts and deleting a fact', async () => {
    mockListLivingFacts.mockResolvedValueOnce(mockListResponse);
    mockDeleteLivingFact.mockResolvedValueOnce(undefined);

    render(<ProjectLivingFactLedgerCard />);

    await waitFor(() => {
      expect(mockListLivingFacts).toHaveBeenCalled();
    });

    // Filter by decision
    const decisionFilterBtn = screen.getByRole('button', { name: /^decision$/i });
    fireEvent.click(decisionFilterBtn);

    expect(screen.getByText('采用单文件嵌入式 sqlite-vec 存储')).toBeInTheDocument();
    expect(screen.queryByText('单文件行数不超过 400 行')).not.toBeInTheDocument();

    // Switch back to all
    const allFilterBtn = screen.getByRole('button', { name: /全部/i });
    fireEvent.click(allFilterBtn);

    // Delete a fact
    const deleteBtn = screen.getByRole('button', { name: /删除 否决 Milvus 外部独立容器/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(mockDeleteLivingFact).toHaveBeenCalledWith('default-project', 'fact-rej-01');
    });
    expect(screen.queryByText('否决 Milvus 外部独立容器')).not.toBeInTheDocument();
  });

  it('records a new living fact in the ledger', async () => {
    mockListLivingFacts.mockResolvedValue(mockListResponse);
    mockRecordLivingFact.mockResolvedValueOnce({
      fact_id: 'fact-new-99',
      project_id: 'default-project',
      fact_type: 'decision',
      title: '采用 TypeScript 严格类型',
      content: '杜绝 any 类型注解，强制显式接口定义。',
      target_components: ['frontend', 'types'],
      reason_or_constraint: '工程严谨性',
      validation_count: 0,
      regression_count: 0,
      promotion_stage: 'confirmed_fact',
      created_at: '2026-10-08T01:00:00Z',
      updated_at: '2026-10-08T01:00:00Z',
      metadata: {},
    });

    render(<ProjectLivingFactLedgerCard />);

    await waitFor(() => {
      expect(mockListLivingFacts).toHaveBeenCalled();
    });

    fireEvent.change(screen.getByLabelText(/标题 \(Title\):/i), {
      target: { value: '采用 TypeScript 严格类型' },
    });
    fireEvent.change(screen.getByLabelText(/详细内容描述 \(Content\):/i), {
      target: { value: '杜绝 any 类型注解，强制显式接口定义。' },
    });
    fireEvent.change(screen.getByLabelText(/关联组件\/模块/i), {
      target: { value: 'frontend, types' },
    });
    fireEvent.change(screen.getByLabelText(/依据 \/ 否决理由:/i), {
      target: { value: '工程严谨性' },
    });

    const submitBtn = screen.getByRole('button', { name: /登记入项目事实账本/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRecordLivingFact).toHaveBeenCalledWith(
        'default-project',
        expect.objectContaining({
          title: '采用 TypeScript 严格类型',
          content: '杜绝 any 类型注解，强制显式接口定义。',
          target_components: ['frontend', 'types'],
          reason_or_constraint: '工程严谨性',
        }),
      );
    });
  });

  it('runs 4-tier context projection simulation', async () => {
    mockListLivingFacts.mockResolvedValueOnce(mockListResponse);
    mockProjectContext.mockResolvedValueOnce(mockProjectionResponse);

    render(<ProjectLivingFactLedgerCard />);

    await waitFor(() => {
      expect(mockListLivingFacts).toHaveBeenCalled();
    });

    // Switch to projection tab
    const projectionTabBtn = screen.getByRole('button', { name: /4-Tier 投影仿真器/i });
    fireEvent.click(projectionTabBtn);

    expect(screen.getByText(/四层级联动态上下文投影器/i)).toBeInTheDocument();

    const runBtn = screen.getByRole('button', { name: /执行四层级联投影装配/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(mockProjectContext).toHaveBeenCalledWith(
        'default-project',
        expect.objectContaining({
          token_budget: 1500,
        }),
      );
    });

    expect(await screen.findByText(/投影装配成果 \(Token 预估: 380 \/ 1500\)/i)).toBeInTheDocument();
    expect(screen.getByText(/节约 Token: 1120/i)).toBeInTheDocument();
    expect(screen.getByText(/Rule Layer:/i)).toBeInTheDocument();
    expect(screen.getByText(/\[PROJECT_STATE: default-project\]/i)).toBeInTheDocument();
  });

  it('executes validation audit and triggers promotion flywheel', async () => {
    mockListLivingFacts.mockResolvedValue(mockListResponse);
    mockAuditValidation.mockResolvedValueOnce(mockAuditResponse);

    render(<ProjectLivingFactLedgerCard />);

    await waitFor(() => {
      expect(mockListLivingFacts).toHaveBeenCalled();
    });

    // Switch to audit tab
    const auditTabBtn = screen.getByRole('button', { name: /验证晋升审计/i });
    fireEvent.click(auditTabBtn);

    expect(screen.getByText(/基于确定性验证的经验准入网关/i)).toBeInTheDocument();

    const auditBtn = screen.getByRole('button', { name: /执行验证审计并触发晋升飞轮/i });
    fireEvent.click(auditBtn);

    await waitFor(() => {
      expect(mockAuditValidation).toHaveBeenCalledWith(
        'default-project',
        expect.objectContaining({
          fact_id: 'fact-dec-01',
          passed: true,
        }),
      );
    });

    expect(await screen.findByText(/经验成功晋升至 knowledge 阶段/i)).toBeInTheDocument();
    expect(screen.getByText('confirmed_fact')).toBeInTheDocument();
    expect(screen.getByText('knowledge')).toBeInTheDocument();
  });
});
