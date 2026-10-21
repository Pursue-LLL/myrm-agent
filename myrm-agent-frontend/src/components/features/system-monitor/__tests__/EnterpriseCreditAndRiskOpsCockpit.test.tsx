import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EnterpriseCreditAndRiskOpsCockpit } from '../EnterpriseCreditAndRiskOpsCockpit';
import type { EnterpriseCockpitData } from '../enterpriseCreditCockpitTypes';

describe('EnterpriseCreditAndRiskOpsCockpit', () => {
  const mockCockpitData: EnterpriseCockpitData = {
    total_credit_quota: 100000,
    total_credit_spent: 12500,
    available_credit: 87500,
    utilization_pct: 12.5,
    is_quota_breached: false,
    warning_threshold_pct: 80,
    total_audit_records: 3,
    risk_event_count: 2,
    blocked_count: 1,
    allocations_by_surface: [
      { surface_name: 'webui', credit_spent: 4500, request_count: 120 },
      { surface_name: 'desktop', credit_spent: 5000, request_count: 85 },
      { surface_name: 'cloud_sandbox', credit_spent: 3000, request_count: 30 },
      { surface_name: 'mobile', credit_spent: 0, request_count: 0 },
    ],
    recent_audit_records: [
      {
        record_id: 'rec_001',
        actor_id: 'emp_alice',
        product_surface: 'webui',
        interaction_summary: 'Generate weekly team summary',
        data_object_scope: 'knowledge.wiki',
        credit_consumed: 15,
        risk_level: 'NONE',
        risk_behavior: 'NONE',
        policy_verdict: 'ALLOW',
        timestamp_ms: 1710000001000,
      },
      {
        record_id: 'rec_002',
        actor_id: 'emp_bob',
        product_surface: 'desktop',
        interaction_summary: 'Query customer contacts',
        data_object_scope: 'crm.leads',
        credit_consumed: 45,
        risk_level: 'MEDIUM',
        risk_behavior: 'RATE_SPIKE',
        policy_verdict: 'AUDIT',
        timestamp_ms: 1710000002000,
      },
      {
        record_id: 'rec_003',
        actor_id: 'emp_charlie',
        product_surface: 'cloud_sandbox',
        interaction_summary: 'Mass export employee records',
        data_object_scope: 'hr.payroll',
        credit_consumed: 120,
        risk_level: 'CRITICAL',
        risk_behavior: 'SENSITIVE_DATA_EXPORT',
        policy_verdict: 'BLOCKED',
        timestamp_ms: 1710000003000,
      },
    ],
  };

  it('renders cockpit with unified metrics, surface allocations, and audit trail', () => {
    const onRefresh = vi.fn();
    const onReset = vi.fn();

    render(
      <EnterpriseCreditAndRiskOpsCockpit
        cockpitData={mockCockpitData}
        onRefresh={onRefresh}
        onReset={onReset}
      />
    );

    // 标题与人时数险徽章
    expect(
      screen.getByText('企业用量与风险运营驾驶舱 (Enterprise Credit & Risk Cockpit)')
    ).toBeInTheDocument();
    expect(screen.getByText('人·时·数·险同链路')).toBeInTheDocument();

    // 核心 KPI
    expect(screen.getByText('100,000')).toBeInTheDocument();
    expect(screen.getByText('12,500')).toBeInTheDocument();
    expect(screen.getByText('87,500')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument(); // blocked_count
    expect(screen.getByText(/风险事件: 2 起/)).toBeInTheDocument();

    // 跨端分布
    expect(screen.getByText('4500 点')).toBeInTheDocument();
    expect(screen.getByText('5000 点')).toBeInTheDocument();
    expect(screen.getByText('3000 点')).toBeInTheDocument();

    // 审计表格
    expect(screen.getByText('emp_alice')).toBeInTheDocument();
    expect(screen.getByText('emp_bob')).toBeInTheDocument();
    expect(screen.getByText('emp_charlie')).toBeInTheDocument();
    expect(screen.getByText('hr.payroll')).toBeInTheDocument();
  });

  it('filters audit records by risk severity', () => {
    render(<EnterpriseCreditAndRiskOpsCockpit cockpitData={mockCockpitData} />);

    // 过滤 CRITICAL 风险
    const criticalBtn = screen.getByRole('button', { name: 'CRITICAL' });
    fireEvent.click(criticalBtn);

    expect(screen.getByText('emp_charlie')).toBeInTheDocument();
    expect(screen.queryByText('emp_alice')).not.toBeInTheDocument();
    expect(screen.queryByText('emp_bob')).not.toBeInTheDocument();
  });

  it('opens quota modal and submits new quota parameters', async () => {
    const onConfigureQuota = vi.fn().mockResolvedValue(undefined);

    render(
      <EnterpriseCreditAndRiskOpsCockpit
        cockpitData={mockCockpitData}
        onConfigureQuota={onConfigureQuota}
      />
    );

    // 点击打开配额弹窗
    const openModalBtn = screen.getByRole('button', { name: '调整企业配额' });
    fireEvent.click(openModalBtn);

    expect(screen.getByText('调整企业 Credit 配额')).toBeInTheDocument();

    // 提交新配额
    const submitBtn = screen.getByRole('button', { name: '确认更新' });
    await React.act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(onConfigureQuota).toHaveBeenCalledWith(100000, 80);
  });

  it('renders breach warning badge when quota is breached', () => {
    const breachedData: EnterpriseCockpitData = {
      ...mockCockpitData,
      is_quota_breached: true,
      available_credit: 0,
      utilization_pct: 105.0,
    };

    render(<EnterpriseCreditAndRiskOpsCockpit cockpitData={breachedData} />);
    expect(screen.getByText('⚠️ 额度耗尽熔断')).toBeInTheDocument();
  });
});
