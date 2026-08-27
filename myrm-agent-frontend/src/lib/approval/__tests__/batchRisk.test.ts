import { describe, it, expect } from 'vitest';
import { classifyBatchApprovalRisk, classifySingleApprovalRisk } from '../batchRisk';
import type { ApprovalPayload } from '@/store/useApprovalStore';

describe('batchRisk classification logic', () => {
  it('correctly classifies safe approvals', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-1',
      user_id: 'u1',
      action_type: 'read_file',
      status: 'PENDING',
      severity: 'info',
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('safe');
  });

  it('correctly classifies high risk when severity is critical', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-2',
      user_id: 'u1',
      action_type: 'custom_op',
      status: 'PENDING',
      severity: 'critical',
      reason: 'Root access requested',
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('high');
    expect(res.reason).toBe('Root access requested');
  });

  it('correctly classifies smartDenied in reviewConfigs', () => {
    const item: ApprovalPayload = {
      approval_id: 'appr-3',
      user_id: 'u1',
      action_type: 'subagent_approval',
      status: 'PENDING',
      severity: 'info',
      payload: {
        reviewConfigs: [{ smartDenied: true }],
      },
    };
    const res = classifySingleApprovalRisk(item);
    expect(res.riskLevel).toBe('high');
  });

  it('generates a full batch report with safe and high-risk separation', () => {
    const items: ApprovalPayload[] = [
      {
        approval_id: 'safe-1',
        user_id: 'u1',
        action_type: 'read_file',
        status: 'PENDING',
        severity: 'info',
      },
      {
        approval_id: 'high-1',
        user_id: 'u1',
        action_type: 'delete_file',
        status: 'PENDING',
        severity: 'high',
      },
    ];

    const report = classifyBatchApprovalRisk(items);
    expect(report.hasHighRisk).toBe(true);
    expect(report.totalCount).toBe(2);
    expect(report.highRiskCount).toBe(1);
    expect(report.safeCount).toBe(1);
    expect(report.safeItemIds).toEqual(['safe-1']);
    expect(report.highRiskItems[0].itemId).toBe('high-1');
  });
});
