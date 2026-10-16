/** @vitest-environment jsdom */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCuratorDiagnostics } from '../useCuratorDiagnostics';
import type { SkillDoctorDiagnosticsResponse, SkillRemediationResponse } from '@/services/skill';

const getSkillDiagnosticsMock = vi.hoisted(() => vi.fn());
const remediateSkillFindingMock = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({ useTranslations: () => (key: string) => key }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));
vi.mock('@/services/skill', () => ({
  getSkillDiagnostics: getSkillDiagnosticsMock,
  remediateSkillFinding: remediateSkillFindingMock,
}));

const report: SkillDoctorDiagnosticsResponse = {
  health_score: 85,
  findings: [
    {
      skill_name: 'daily-report',
      finding_type: 'wrong_but_frequent',
      severity: 'warning',
      call_count: 12,
      success_rate: 0.2,
      pinned: false,
      bound: false,
      details: { observed_count: 12 },
    },
  ],
};

const done: SkillRemediationResponse = { success: true, skill_name: 'daily-report' };

describe('useCuratorDiagnostics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSkillDiagnosticsMock.mockResolvedValue(report);
  });

  it('loads the report on demand and drops it when the server cannot produce one', async () => {
    const { result } = renderHook(() => useCuratorDiagnostics());

    await act(() => result.current.loadDiagnostics());
    expect(result.current.diagnostics).toEqual(report);

    getSkillDiagnosticsMock.mockRejectedValueOnce(new Error('down'));
    await act(() => result.current.loadDiagnostics());
    expect(result.current.diagnostics).toBeNull();
  });

  it('reloads the report and notifies the owner after a successful remediation', async () => {
    remediateSkillFindingMock.mockResolvedValue(done);
    const onRemediated = vi.fn();
    const { result } = renderHook(() => useCuratorDiagnostics(onRemediated));

    await act(() => result.current.remediate('daily-report', 'archive'));

    expect(remediateSkillFindingMock).toHaveBeenCalledWith('daily-report', 'archive');
    expect(toastMock).toHaveBeenCalledWith({
      title: 'doctor.remediateSuccessTitle',
      description: 'doctor.remediateSuccessDesc',
    });
    expect(getSkillDiagnosticsMock).toHaveBeenCalledTimes(1);
    expect(onRemediated).toHaveBeenCalledTimes(1);
    expect(result.current.remediatingSkill).toBeNull();
  });

  it('shows the server reason and leaves the report alone when the remediation is refused', async () => {
    remediateSkillFindingMock.mockResolvedValue({ success: false, error: 'Skill is bound' });
    const onRemediated = vi.fn();
    const { result } = renderHook(() => useCuratorDiagnostics(onRemediated));

    await act(() => result.current.remediate('daily-report', 'archive'));

    expect(toastMock).toHaveBeenCalledWith({
      title: 'doctor.remediateFailedTitle',
      description: 'Skill is bound',
      variant: 'destructive',
    });
    expect(getSkillDiagnosticsMock).not.toHaveBeenCalled();
    expect(onRemediated).not.toHaveBeenCalled();
  });

  it('ignores a second remediation while one is still running', async () => {
    let finish: (value: SkillRemediationResponse) => void = () => undefined;
    remediateSkillFindingMock.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { result } = renderHook(() => useCuratorDiagnostics());

    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.remediate('daily-report', 'archive');
    });
    await act(() => result.current.remediate('invoice-ocr', 'archive'));

    expect(remediateSkillFindingMock).toHaveBeenCalledTimes(1);
    expect(result.current.remediatingSkill).toBe('daily-report');

    await act(async () => {
      finish(done);
      await first;
    });
    expect(result.current.remediatingSkill).toBeNull();
  });

  it('reports a request failure and marks only the skill being remediated as busy meanwhile', async () => {
    let fail: (reason: Error) => void = () => undefined;
    remediateSkillFindingMock.mockReturnValue(new Promise((_resolve, reject) => (fail = reject)));
    const { result } = renderHook(() => useCuratorDiagnostics());

    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.remediate('daily-report', 'reset_stats');
    });
    await waitFor(() => expect(result.current.remediatingSkill).toBe('daily-report'));

    await act(async () => {
      fail(new Error('Network down'));
      await pending;
    });

    expect(toastMock).toHaveBeenCalledWith({
      title: 'doctor.remediateFailedTitle',
      description: 'Network down',
      variant: 'destructive',
    });
    expect(result.current.remediatingSkill).toBeNull();
  });
});
