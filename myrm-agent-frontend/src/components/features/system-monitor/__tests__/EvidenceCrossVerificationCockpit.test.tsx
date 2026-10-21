import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EvidenceCrossVerificationCockpit } from '../EvidenceCrossVerificationCockpit';
import type { VerificationFindingData } from '../evidenceCrossVerificationTypes';

describe('EvidenceCrossVerificationCockpit', () => {
  const mockFinding: VerificationFindingData = {
    diagnosis_id: 'diag_test_9001',
    error_code: 'ERR_GATEWAY_TIMEOUT',
    resolved_code_meaning: 'ERR_PAYMENT_GATEWAY_TIMEOUT (Payment Gateway Deadline Exceeded)',
    target_file_path: 'app/services/checkout.py',
    target_line_number: 58,
    root_cause_category: 'CUMULATIVE_TIMEOUT',
    explanation: 'Root cause analyzed for event date 2026-10-13. Cumulative serial loop exceeded 5000ms deadline.',
    recommended_patch: 'Replace sequential loop with asyncio.gather() or set strict socket timeout deadline.',
    confidence_score: 4,
    confidence_level: 'HIGH',
    evidences: [
      {
        source_type: 'KNOWLEDGE_BASE',
        title: 'Payment SLA Runbook',
        detail: 'Gateway maximum execution deadline is 3000ms',
        is_verified: true,
        timestamp_ms: 1710000001000,
        weight: 1.0,
        file_path: '',
        line_number: 0,
        trace_id: '',
      },
      {
        source_type: 'CODE_SYMBOL',
        title: 'PaymentRouter Definition',
        detail: 'Function route_checkout located',
        is_verified: true,
        timestamp_ms: 1710000002000,
        weight: 1.0,
        file_path: 'app/services/checkout.py',
        line_number: 42,
        trace_id: '',
      },
      {
        source_type: 'SOURCE_LOGIC',
        title: 'Serial Retry Loop',
        detail: 'Synchronous loop awaiting sequential downstream calls',
        is_verified: true,
        timestamp_ms: 1710000003000,
        weight: 1.0,
        file_path: 'app/services/checkout.py',
        line_number: 58,
        trace_id: '',
      },
      {
        source_type: 'RUNTIME_TELEMETRY',
        title: 'Distributed Trace Span',
        detail: 'Trace observed cumulative timeout of 5800ms before aborting',
        is_verified: true,
        timestamp_ms: 1710000004000,
        weight: 1.0,
        file_path: '',
        line_number: 0,
        trace_id: 'tr_pay_9981',
      },
    ],
    bilateral_verified: true,
    created_at_ms: 1710000005000,
  };

  it('renders header, 4-tier confidence badge, root cause cards, and patch recommendation', () => {
    const onDiagnose = vi.fn();
    const onReset = vi.fn();

    render(
      <EvidenceCrossVerificationCockpit
        activeFinding={mockFinding}
        onDiagnose={onDiagnose}
        onReset={onReset}
      />
    );

    // 头部信息
    expect(screen.getByText('多源证据交叉验证与四分制置信度排障大盘')).toBeInTheDocument();
    expect(screen.getByText('四维立体现证引擎')).toBeInTheDocument();

    // 诊断核心卡片
    expect(screen.getByText('ERR_GATEWAY_TIMEOUT')).toBeInTheDocument();
    expect(screen.getByText(/ERR_PAYMENT_GATEWAY_TIMEOUT/)).toBeInTheDocument();
    expect(screen.getByText('极高置信度 (4/4 分 · 建议采纳)')).toBeInTheDocument();
    expect(screen.getByText('✓ 前后端双向调用契约验证通过')).toBeInTheDocument();
    expect(screen.getByText('CUMULATIVE_TIMEOUT')).toBeInTheDocument();
    expect(screen.getByText('app/services/checkout.py:58')).toBeInTheDocument();

    // 行动派修复建议卡片
    expect(screen.getByText(/行动派修复补丁建议/)).toBeInTheDocument();
    expect(
      screen.getByText(/Replace sequential loop with asyncio.gather\(\)/)
    ).toBeInTheDocument();

    // 四维证据链
    expect(screen.getByText('Payment SLA Runbook')).toBeInTheDocument();
    expect(screen.getByText('PaymentRouter Definition')).toBeInTheDocument();
    expect(screen.getByText('Serial Retry Loop')).toBeInTheDocument();
    expect(screen.getByText('Distributed Trace Span')).toBeInTheDocument();
    expect(screen.getByText('Span: tr_pay_9981')).toBeInTheDocument();
  });

  it('triggers onDiagnose with input error code and onReset callbacks', async () => {
    const onDiagnose = vi.fn().mockResolvedValue(undefined);
    const onReset = vi.fn().mockResolvedValue(undefined);

    render(
      <EvidenceCrossVerificationCockpit
        activeFinding={mockFinding}
        onDiagnose={onDiagnose}
        onReset={onReset}
      />
    );

    const input = screen.getByPlaceholderText('输入故障错误码...');
    fireEvent.change(input, { target: { value: 'CUSTOM_ERR_500' } });

    const diagnoseBtn = screen.getByRole('button', { name: '发起多源立体现证' });
    await React.act(async () => {
      fireEvent.click(diagnoseBtn);
    });
    expect(onDiagnose).toHaveBeenCalledWith('CUSTOM_ERR_500');

    const resetBtn = screen.getByRole('button', { name: '重置证据池' });
    await React.act(async () => {
      fireEvent.click(resetBtn);
    });
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('renders empty state when no active finding is supplied', () => {
    render(<EvidenceCrossVerificationCockpit activeFinding={null} />);
    expect(
      screen.getByText('暂无活跃排障结论，请输入错误码并发起多源立体现证')
    ).toBeInTheDocument();
  });

  it('renders recent diagnoses list and allows clicking to view details', () => {
    const recent = [
      {
        ...mockFinding,
        diagnosis_id: 'diag_hist_1',
        error_code: 'HIST_DOWNSTREAM_502',
        confidence_level: 'MEDIUM' as const,
        confidence_score: 2,
      },
    ];

    render(
      <EvidenceCrossVerificationCockpit
        activeFinding={null}
        recentDiagnoses={recent}
      />
    );

    expect(screen.getByText('📜 最近排查诊断历史卷宗')).toBeInTheDocument();
    expect(screen.getByText('HIST_DOWNSTREAM_502')).toBeInTheDocument();
    expect(screen.getByText('MEDIUM (2/4)')).toBeInTheDocument();

    // 点击历史项展开
    const histItem = screen.getByText('HIST_DOWNSTREAM_502');
    fireEvent.click(histItem);

    // 应该展示详情
    expect(screen.getByText('中等置信度 (2/4 分 · 需人工复核)')).toBeInTheDocument();
  });
});
