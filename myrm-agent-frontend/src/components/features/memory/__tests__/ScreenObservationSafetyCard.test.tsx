/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ScreenObservationSafetyCard } from '../command-center/ScreenObservationSafetyCard';
import type {
  ScreenSafetyAuditListResponseDTO,
  ScreenObservationSafetyResponseDTO,
} from '@/services/memory/screenObservationSafety';

const {
  mockProcessScreenObservation,
  mockGetScreenObservationAuditRecords,
} = vi.hoisted(() => ({
  mockProcessScreenObservation: vi.fn(),
  mockGetScreenObservationAuditRecords: vi.fn(),
}));

vi.mock('@/services/memory/screenObservationSafety', () => ({
  processScreenObservation: mockProcessScreenObservation,
  getScreenObservationAuditRecords: mockGetScreenObservationAuditRecords,
}));

describe('ScreenObservationSafetyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAuditRecordsEmpty: ScreenSafetyAuditListResponseDTO = {
    total_count: 0,
    records: [],
  };

  const mockAuditRecordsFilled: ScreenSafetyAuditListResponseDTO = {
    total_count: 2,
    records: [
      {
        record_id: 'rec-001',
        session_id: 'sess-001',
        created_at: '2026-10-08T02:00:00Z',
        app_name: 'VSCode',
        fact_statement: '用户在 VSCode 中编辑了 API 服务代码',
        risk_score: 0.05,
        promotion_status: 'transient_observation',
        imperative_detected: false,
      },
      {
        record_id: 'rec-002',
        session_id: 'sess-002',
        created_at: '2026-10-08T02:05:00Z',
        app_name: 'Chrome',
        fact_statement: '',
        risk_score: 0.95,
        promotion_status: 'rejected_injection',
        imperative_detected: false,
      },
    ],
  };

  const mockSafeResponse: ScreenObservationSafetyResponseDTO = {
    audit_id: 'aud-safe-101',
    is_safe: true,
    risk_score: 0.02,
    detected_injection_patterns: [],
    promotion_status: 'transient_observation',
    is_promoted: false,
    final_statement: '用户在终端中运行了测试并通过',
    imperative_detected: false,
    explanation: '符合客观第三人称描述性语法，单次会话保留为临时活动记录。',
    isolated_prompt_preview: '<observed_visual_evidence source="ax_tree">...</observed_visual_evidence>',
  };

  const mockInjectionResponse: ScreenObservationSafetyResponseDTO = {
    audit_id: 'aud-inj-202',
    is_safe: false,
    risk_score: 0.98,
    detected_injection_patterns: ['ignore_instructions', 'credential_leak_attempt'],
    promotion_status: 'rejected_injection',
    is_promoted: false,
    final_statement: '',
    imperative_detected: false,
    explanation: '检出高危提示词注入攻击向量，已被彻底阻断拒绝入库。',
    isolated_prompt_preview: '<observed_visual_evidence source="browser_dom">[REDACTED]</observed_visual_evidence>',
  };

  const mockImperativeAndPromotedResponse: ScreenObservationSafetyResponseDTO = {
    audit_id: 'aud-prom-303',
    is_safe: true,
    risk_score: 0.04,
    detected_injection_patterns: [],
    promotion_status: 'promoted_preference',
    is_promoted: true,
    final_statement: '用户习惯在全系统中启用深色模式主题',
    imperative_detected: true,
    explanation: '检测到祈使动词并重写为第三人称；跨会话频次校验达标晋升为偏好。',
    isolated_prompt_preview: '<observed_visual_evidence source="screenshot_summary">...</observed_visual_evidence>',
  };

  it('renders initial state and loads audit records', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValueOnce(mockAuditRecordsFilled);

    render(<ScreenObservationSafetyCard />);

    expect(screen.getByTestId('screen-observation-safety-card')).toBeInTheDocument();
    expect(screen.getByText(/屏幕与桌面观测型记忆防注入与描述性事实门禁/)).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetScreenObservationAuditRecords).toHaveBeenCalledWith(10);
    });

    expect(await screen.findByText('用户在 VSCode 中编辑了 API 服务代码')).toBeInTheDocument();
    expect(screen.getByText('(已阻断)')).toBeInTheDocument();
  });

  it('renders empty placeholder when no audit records are returned', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValueOnce(mockAuditRecordsEmpty);

    render(<ScreenObservationSafetyCard />);

    expect(await screen.findByText('暂无审计记录')).toBeInTheDocument();
  });

  it('switches form fields when quick test presets are clicked', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValueOnce(mockAuditRecordsEmpty);

    render(<ScreenObservationSafetyCard />);

    const injectionPresetBtn = screen.getByRole('button', { name: /高危提示词注入攻击/ });
    fireEvent.click(injectionPresetBtn);

    const rawTextarea = screen.getByLabelText(/屏幕原始不可信内容/) as HTMLTextAreaElement;
    expect(rawTextarea.value).toContain('Ignore all previous instructions');

    const appInput = screen.getByLabelText(/所属应用/) as HTMLInputElement;
    expect(appInput.value).toBe('Chrome');

    const imperativePresetBtn = screen.getByRole('button', { name: /祈使句自动重写/ });
    fireEvent.click(imperativePresetBtn);

    const statementInput = screen.getByLabelText(/拟提取的事实陈述/) as HTMLInputElement;
    expect(statementInput.value).toContain('Run bun run lint');
  });

  it('processes safe descriptive observation and displays HUD verdict', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValue(mockAuditRecordsEmpty);
    mockProcessScreenObservation.mockResolvedValueOnce(mockSafeResponse);

    render(<ScreenObservationSafetyCard />);

    const submitBtn = screen.getByRole('button', { name: /执行防注入隔离与语法门禁检验/ });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/门禁裁决: 安全放行 \(Passed\)/)).toBeInTheDocument();
    expect(screen.getByText(/风险分: 2%/)).toBeInTheDocument();
    expect(screen.getAllByText(/符合客观第三人称描述性语法/)[0]).toBeInTheDocument();
    expect(screen.getByText(/保持为临时活动观察，拒绝单次过度泛化/)).toBeInTheDocument();
    expect(screen.getByText('用户在终端中运行了测试并通过')).toBeInTheDocument();
  });

  it('processes injection sample and flags security alert with pattern badges', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValue(mockAuditRecordsEmpty);
    mockProcessScreenObservation.mockResolvedValueOnce(mockInjectionResponse);

    render(<ScreenObservationSafetyCard />);

    const submitBtn = screen.getByRole('button', { name: /执行防注入隔离与语法门禁检验/ });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/门禁裁决: 攻击阻断 \(Rejected\)/)).toBeInTheDocument();
    expect(screen.getByText(/检出高危提示词注入攻击模式:/)).toBeInTheDocument();
    expect(screen.getByText('ignore_instructions')).toBeInTheDocument();
    expect(screen.getByText('credential_leak_attempt')).toBeInTheDocument();
  });

  it('processes imperative statement and reflects auto-rewrite and preference promotion', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValue(mockAuditRecordsEmpty);
    mockProcessScreenObservation.mockResolvedValueOnce(mockImperativeAndPromotedResponse);

    render(<ScreenObservationSafetyCard />);

    const submitBtn = screen.getByRole('button', { name: /执行防注入隔离与语法门禁检验/ });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/检测到祈使句动作指令，已自动重写为第三人称/)).toBeInTheDocument();
    expect(screen.getByText(/跨会话频次验证达标，已提升为稳定偏好/)).toBeInTheDocument();
    expect(screen.getByText('用户习惯在全系统中启用深色模式主题')).toBeInTheDocument();
  });

  it('falls back to offline resilient verdict when API request fails', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValue(mockAuditRecordsEmpty);
    mockProcessScreenObservation.mockRejectedValueOnce(new Error('Network offline'));

    render(<ScreenObservationSafetyCard />);

    const submitBtn = screen.getByRole('button', { name: /执行防注入隔离与语法门禁检验/ });
    fireEvent.click(submitBtn);

    expect(await screen.findByText(/门禁裁决: 安全放行 \(Passed\)/)).toBeInTheDocument();
    expect(screen.getByText(/Single-occurrence observation; preserved as transient activity log/)).toBeInTheDocument();
  });

  it('refreshes audit records when refresh button is clicked', async () => {
    mockGetScreenObservationAuditRecords.mockResolvedValue(mockAuditRecordsEmpty);

    render(<ScreenObservationSafetyCard />);

    await waitFor(() => {
      expect(mockGetScreenObservationAuditRecords).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByRole('button', { name: /刷新流水/ });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetScreenObservationAuditRecords).toHaveBeenCalledTimes(2);
    });
  });
});
