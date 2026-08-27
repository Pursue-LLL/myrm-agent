import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import ReportTab from '../tabs/ReportTab';
import type { ReportItem } from '../hooks/useCasesEval';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

function baseProps(overrides: Partial<ReportItem> = {}) {
  return {
    running: false,
    evalStage: null,
    progress: { total: 1, completed: 1 },
    downloadProgress: null,
    report: {
      total: 1,
      passed: 1,
      cases: [
        {
          passed: true,
          actual_output: 'answer',
          case: { message: 'research X' },
        },
      ],
      ...overrides,
    } as ReportItem,
    onViewDiff: vi.fn(),
  };
}

describe('ReportTab trajectory disclosure', () => {
  it('shows the limit badge when a case was stopped by a run budget', () => {
    render(
      <ReportTab
        {...baseProps({
          cases: [
            {
              passed: false,
              actual_output: '',
              limit_reached: 'max_tool_calls',
              case: { message: 'deep research' },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('evalLab.report.limitHit')).toBeInTheDocument();
  });

  it('shows the blocked badge with the guard rejection count', () => {
    render(
      <ReportTab
        {...baseProps({
          cases: [
            {
              passed: false,
              actual_output: '',
              blocked_count: 2,
              case: { message: 'fetch sources' },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('evalLab.report.blocked 2')).toBeInTheDocument();
  });

  it('shows the tool-call count from the recorded trajectory', () => {
    render(
      <ReportTab
        {...baseProps({
          cases: [
            {
              passed: true,
              actual_output: 'answer',
              tool_call_details: [
                { tool_name: 'web_search_tool', step_key: 'web_search_tool' },
                { tool_name: 'web_fetch_tool', step_key: 'web_fetch_tool' },
              ],
              case: { message: 'research X' },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('2×')).toBeInTheDocument();
  });

  it('combines limit and blocked badges on the same case', () => {
    render(
      <ReportTab
        {...baseProps({
          cases: [
            {
              passed: false,
              actual_output: '',
              limit_reached: 'max_tool_calls',
              blocked_count: 1,
              tool_call_details: [{ tool_name: 'web_search_tool', step_key: 'web_search_tool' }],
              case: { message: 'web research' },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('evalLab.report.limitHit')).toBeInTheDocument();
    expect(screen.getByText('evalLab.report.blocked 1')).toBeInTheDocument();
    expect(screen.getByText('1×')).toBeInTheDocument();
  });

  it('renders no badges when the case has no trajectory metadata', () => {
    render(
      <ReportTab
        {...baseProps({
          cases: [
            {
              passed: true,
              actual_output: 'answer',
              case: { message: 'plain case' },
            },
          ],
        })}
      />,
    );

    expect(screen.queryByText('evalLab.report.limitHit')).not.toBeInTheDocument();
    expect(screen.queryByText(/evalLab\.report\.blocked/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+×/)).not.toBeInTheDocument();
  });

  it('renders canary verification and anti-contamination violation details', () => {
    render(
      <ReportTab
        {...baseProps({
          cases: [
            {
              passed: false,
              actual_output: '',
              canary_verified: true,
              contamination_audit: {
                cheat_detected: true,
                violations: [
                  {
                    violation_type: 'hidden_path_accessed',
                    details: 'Agent attempted to probe /hidden_tests/secret.py',
                    tool_name: 'bash',
                    target: '/hidden_tests/secret.py',
                  },
                ],
              },
              case: { message: 'cheat attempt case' },
            },
          ],
        })}
      />,
    );

    expect(screen.getByText('Canary')).toBeInTheDocument();
    expect(screen.getByText('evalLab.report.contaminationViolation')).toBeInTheDocument();
    expect(screen.getByText('[bash] Agent attempted to probe /hidden_tests/secret.py')).toBeInTheDocument();
  });
});
