/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/jobCompounding::getJobDescription, saveJobDescription, listCompoundedRules,
 *   recordCompoundedRule, evaluateMaturity, checkApprovalBoundary
 * ../command-center/JobCompoundingCard::JobCompoundingCard
 *
 * [OUTPUT]
 * Test suite verifying domain-specific agent job description 4-pillar builder,
 * preference compounding, maturity growth ladder, and approval gate simulator.
 *
 * [POS]
 * Unit test for Item 90 (Domain-Specific Agent Job Description and Preference Compounding Suite).
 * Strict typing applied: No `any` types allowed.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { JobCompoundingCard } from '../command-center/JobCompoundingCard';
import type {
  JobDescriptionSpecDTO,
  CompoundedRuleDTO,
  CompoundingMaturityReportDTO,
  CheckApprovalResponseDTO,
} from '@/services/memory/jobCompounding';

const {
  mockGetJobDescription,
  mockSaveJobDescription,
  mockListCompoundedRules,
  mockRecordCompoundedRule,
  mockEvaluateMaturity,
  mockCheckApprovalBoundary,
} = vi.hoisted(() => ({
  mockGetJobDescription: vi.fn(),
  mockSaveJobDescription: vi.fn(),
  mockListCompoundedRules: vi.fn(),
  mockRecordCompoundedRule: vi.fn(),
  mockEvaluateMaturity: vi.fn(),
  mockCheckApprovalBoundary: vi.fn(),
}));

vi.mock('@/services/memory/jobCompounding', () => ({
  getJobDescription: mockGetJobDescription,
  saveJobDescription: mockSaveJobDescription,
  listCompoundedRules: mockListCompoundedRules,
  recordCompoundedRule: mockRecordCompoundedRule,
  evaluateMaturity: mockEvaluateMaturity,
  checkApprovalBoundary: mockCheckApprovalBoundary,
}));

describe('JobCompoundingCard', () => {
  const sampleSpec: JobDescriptionSpecDTO = {
    agent_id: 'agent_talent_scout_01',
    job_title: 'Talent Scout (人才搜寻员)',
    target_scope: '持续寻找高潜技术架构师简历，长期积累筛选偏好形成复利',
    tools_and_sources: ['web_search', 'resume_parser', 'table_analytics'],
    work_style: 'rigorous',
    approval_boundary: {
      autonomous_actions: ['scan_resumes', 'summarize_profile', 'tag_candidate'],
      requires_approval_actions: ['send_interview_invite', 'reject_candidate', 'contact_headhunter'],
    },
    created_at: '2026-10-08T01:00:00Z',
    updated_at: '2026-10-08T01:30:00Z',
  };

  const sampleRules: CompoundedRuleDTO[] = [
    {
      rule_id: 'rule_01',
      agent_id: 'agent_talent_scout_01',
      rule_type: 'positive_preference',
      statement: '优先推荐具备单机 10w+ QPS 真实压测与内核调优经验的候选人',
      trigger_condition: 'on_domain_task_execution',
      evidence_source: 'human_feedback_alignment',
      hit_count: 12,
      created_at: '2026-10-08T02:00:00Z',
    },
    {
      rule_id: 'rule_02',
      agent_id: 'agent_talent_scout_01',
      rule_type: 'negative_constraint',
      statement: '排除简历中仅有调包经验且未深入分布式底层源码者',
      trigger_condition: 'on_domain_task_execution',
      evidence_source: 'human_feedback_alignment',
      hit_count: 5,
      created_at: '2026-10-08T02:15:00Z',
    },
  ];

  const sampleMaturity: CompoundingMaturityReportDTO = {
    agent_id: 'agent_talent_scout_01',
    job_title: 'Talent Scout (人才搜寻员)',
    total_rules_count: 2,
    positive_preferences_count: 1,
    negative_constraints_count: 1,
    inspection_lessons_count: 0,
    maturity_score: 89.0,
    tier: 'specialist',
    summary: '该智能体已积累了多条高价值招聘偏好规则与审批校准记录，复利成熟度达到 89%',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetJobDescription.mockResolvedValue(sampleSpec);
    mockListCompoundedRules.mockResolvedValue(sampleRules);
    mockEvaluateMaturity.mockResolvedValue(sampleMaturity);
  });

  it('renders correctly, loads spec, and displays HUD statistics', async () => {
    render(<JobCompoundingCard />);

    expect(screen.getByTestId('job-compounding-card')).toBeInTheDocument();
    expect(screen.getByText(/业务岗位说明书与经验复利沉淀套件/)).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetJobDescription).toHaveBeenCalledWith('agent_talent_scout_01');
      expect(screen.getByTestId('hud-job-title')).toHaveTextContent('Talent Scout (人才搜寻员)');
      expect(screen.getByTestId('hud-tier')).toHaveTextContent('specialist');
      expect(screen.getByTestId('hud-rules-count')).toHaveTextContent('2 条');
      expect(screen.getByTestId('hud-approval-count')).toHaveTextContent('3 项');
    });
  });

  it('switches between presets (e.g. Bug Reproduction)', async () => {
    const bugReproSpec: JobDescriptionSpecDTO = {
      agent_id: 'agent_bug_repro_01',
      job_title: 'Bug Reproduction (漏洞复现员)',
      target_scope: '每次检查上报漏洞，自动化沙箱复现并积累排查思路与测试用例',
      tools_and_sources: ['test_runner', 'sandbox_exec', 'git_diff'],
      work_style: 'rigorous',
      approval_boundary: {
        autonomous_actions: ['checkout_code', 'run_tests', 'collect_logs'],
        requires_approval_actions: ['merge_hotfix', 'deploy_staging', 'restart_cluster'],
      },
      created_at: '2026-10-08T03:00:00Z',
      updated_at: '2026-10-08T03:10:00Z',
    };
    mockSaveJobDescription.mockResolvedValueOnce(bugReproSpec);

    render(<JobCompoundingCard />);

    await waitFor(() => {
      expect(screen.getByTestId('preset-bug-repro-btn')).toBeInTheDocument();
    });

    const bugReproBtn = screen.getByTestId('preset-bug-repro-btn');
    fireEvent.click(bugReproBtn);

    await waitFor(() => {
      expect(mockSaveJobDescription).toHaveBeenCalledWith(
        expect.objectContaining({
          agent_id: 'agent_bug_repro_01',
          job_title: 'Bug Reproduction (漏洞复现员)',
        })
      );
      expect(screen.getByText(/已保存岗位四要素说明书/)).toBeInTheDocument();
    });
  });

  it('edits and saves 4-pillar job description form', async () => {
    const updatedSpec: JobDescriptionSpecDTO = {
      ...sampleSpec,
      job_title: 'Lead Talent Scout',
      target_scope: '全面负责高端技术人才引进与架构师招募',
    };
    mockSaveJobDescription.mockResolvedValueOnce(updatedSpec);

    render(<JobCompoundingCard />);

    await waitFor(() => {
      expect(screen.getByTestId('job-title-input')).toHaveValue('Talent Scout (人才搜寻员)');
    });

    const titleInput = screen.getByTestId('job-title-input');
    const scopeInput = screen.getByTestId('target-scope-input');

    fireEvent.change(titleInput, { target: { value: 'Lead Talent Scout' } });
    fireEvent.change(scopeInput, { target: { value: '全面负责高端技术人才引进与架构师招募' } });

    const form = screen.getByTestId('job-description-builder-form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(mockSaveJobDescription).toHaveBeenCalledWith(
        expect.objectContaining({
          job_title: 'Lead Talent Scout',
          target_scope: '全面负责高端技术人才引进与架构师招募',
        })
      );
      expect(screen.getByText(/已保存岗位四要素说明书: Lead Talent Scout/)).toBeInTheDocument();
    });
  });

  it('switches to Maturity Tab and displays growth ladder and rules', async () => {
    render(<JobCompoundingCard />);

    const maturityTab = screen.getByTestId('tab-maturity');
    fireEvent.click(maturityTab);

    await waitFor(() => {
      expect(screen.getByTestId('compounding-maturity-view')).toBeInTheDocument();
      expect(screen.getByTestId('maturity-tier-badge')).toHaveTextContent('specialist');
      expect(screen.getByTestId('maturity-score-text')).toHaveTextContent('89.0%');
      expect(screen.getByTestId('rule-item-rule_01')).toBeInTheDocument();
      expect(screen.getByTestId('rule-item-rule_02')).toBeInTheDocument();
    });
  });

  it('compounds and appends a new domain rule', async () => {
    const newRule: CompoundedRuleDTO = {
      rule_id: 'rule_03',
      agent_id: 'agent_talent_scout_01',
      rule_type: 'positive_preference',
      statement: '关注开源项目维护者经历',
      trigger_condition: 'on_domain_task_execution',
      evidence_source: 'human_feedback_alignment',
      hit_count: 1,
      created_at: '2026-10-08T03:30:00Z',
    };
    mockRecordCompoundedRule.mockResolvedValueOnce(newRule);

    render(<JobCompoundingCard />);

    const maturityTab = screen.getByTestId('tab-maturity');
    fireEvent.click(maturityTab);

    await waitFor(() => {
      expect(screen.getByTestId('rule-statement-input')).toBeInTheDocument();
    });

    const statementInput = screen.getByTestId('rule-statement-input');
    fireEvent.change(statementInput, { target: { value: '关注开源项目维护者经历' } });

    const addRuleForm = screen.getByTestId('add-rule-form');
    fireEvent.submit(addRuleForm);

    await waitFor(() => {
      expect(mockRecordCompoundedRule).toHaveBeenCalledWith(
        expect.objectContaining({
          statement: '关注开源项目维护者经历',
        })
      );
      expect(screen.getByText(/已沉淀新领域规则: 关注开源项目维护者经历/)).toBeInTheDocument();
    });
  });

  it('checks approval boundary with gate simulator (blocking action)', async () => {
    const checkResponse: CheckApprovalResponseDTO = {
      agent_id: 'agent_talent_scout_01',
      action_name: 'send_interview_invite',
      needs_approval: true,
      reason: "Action 'send_interview_invite' belongs to requires_approval boundary",
    };
    mockCheckApprovalBoundary.mockResolvedValueOnce(checkResponse);

    render(<JobCompoundingCard />);

    const maturityTab = screen.getByTestId('tab-maturity');
    fireEvent.click(maturityTab);

    await waitFor(() => {
      expect(screen.getByTestId('action-check-input')).toBeInTheDocument();
    });

    const actionInput = screen.getByTestId('action-check-input');
    fireEvent.change(actionInput, { target: { value: 'send_interview_invite' } });

    const checkForm = screen.getByTestId('check-approval-form');
    fireEvent.submit(checkForm);

    await waitFor(() => {
      expect(mockCheckApprovalBoundary).toHaveBeenCalledWith({
        agent_id: 'agent_talent_scout_01',
        action_name: 'send_interview_invite',
      });
      expect(screen.getByTestId('approval-result-card')).toBeInTheDocument();
      expect(screen.getByText(/【阻断】需人工董事长审批/)).toBeInTheDocument();
    });
  });

  it('checks approval boundary with gate simulator (autonomous action)', async () => {
    const checkResponse: CheckApprovalResponseDTO = {
      agent_id: 'agent_talent_scout_01',
      action_name: 'scan_resumes',
      needs_approval: false,
      reason: "Action 'scan_resumes' is explicitly permitted in autonomous actions",
    };
    mockCheckApprovalBoundary.mockResolvedValueOnce(checkResponse);

    render(<JobCompoundingCard />);

    const maturityTab = screen.getByTestId('tab-maturity');
    fireEvent.click(maturityTab);

    await waitFor(() => {
      expect(screen.getByTestId('action-check-input')).toBeInTheDocument();
    });

    const actionInput = screen.getByTestId('action-check-input');
    fireEvent.change(actionInput, { target: { value: 'scan_resumes' } });

    const checkForm = screen.getByTestId('check-approval-form');
    fireEvent.submit(checkForm);

    await waitFor(() => {
      expect(mockCheckApprovalBoundary).toHaveBeenCalledWith({
        agent_id: 'agent_talent_scout_01',
        action_name: 'scan_resumes',
      });
      expect(screen.getByTestId('approval-result-card')).toBeInTheDocument();
      expect(screen.getByText(/【放行】属于自主执行边界/)).toBeInTheDocument();
    });
  });

  it('degrades gracefully when backend calls fail', async () => {
    mockGetJobDescription.mockRejectedValueOnce(new Error('Network error'));
    mockListCompoundedRules.mockRejectedValueOnce(new Error('Network error'));
    mockEvaluateMaturity.mockRejectedValueOnce(new Error('Network error'));

    render(<JobCompoundingCard />);

    await waitFor(() => {
      expect(screen.getByTestId('job-compounding-card')).toBeInTheDocument();
      expect(screen.getByTestId('hud-job-title')).toBeInTheDocument();
    });
  });
});
