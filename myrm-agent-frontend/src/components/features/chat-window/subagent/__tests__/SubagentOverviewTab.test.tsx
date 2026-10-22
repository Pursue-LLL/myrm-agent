// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { toast } from 'sonner';
import { SubagentOverviewTab } from '../SubagentOverviewTab';
import type { SubagentNode } from '@/store/chat/useSubagentStore';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn() },
}));

function makeNode(partial: Partial<SubagentNode>): SubagentNode {
  return {
    task_id: 'subtask-12345678',
    parent_task_id: '',
    agent_type: 'researcher',
    description: 'Investigate documentation',
    status: 'completed',
    progress: 100,
    stream: [],
    ...partial,
  };
}

describe('SubagentOverviewTab', () => {
  const writeText = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  });

  it('renders the handover report with findings, artifacts, citations and checklist', () => {
    render(
      <SubagentOverviewTab
        node={makeNode({
          handover_state: {
            summary: 'All sources reviewed',
            findings: [{ finding: 'API is stable', confidence: 'medium', evidence: 'docs/api.md' }],
            artifact_refs: ['reports/out.md'],
            citations: ['https://example.com/a'],
            task_completed: ['collect sources'],
          },
        })}
      />,
    );

    expect(screen.getByText('All sources reviewed')).toBeDefined();
    expect(screen.getByText('API is stable')).toBeDefined();
    expect(screen.getByText('docs/api.md')).toBeDefined();
    expect(screen.getByText('reports/out.md')).toBeDefined();
    expect(screen.getByText('https://example.com/a')).toBeDefined();
    expect(screen.getByText('collect sources')).toBeDefined();
    expect(screen.getByText('detailConfidenceMedium')).toBeDefined();
  });

  it('labels finding confidence through translation keys and keeps unrecognised levels verbatim', () => {
    render(
      <SubagentOverviewTab
        node={makeNode({
          handover_state: {
            findings: [
              { finding: 'Default level', evidence: '' },
              { finding: 'Odd level', confidence: 'speculative', evidence: '' },
            ],
          },
        })}
      />,
    );

    expect(screen.getByText('detailConfidenceHigh')).toBeDefined();
    expect(screen.getByText('speculative')).toBeDefined();
  });

  it('shows the translated status label instead of the raw status code in the metadata card', () => {
    render(<SubagentOverviewTab node={makeNode({ status: 'timed_out', progress: 40 })} />);

    expect(screen.getByText('40% (statusLabel.timed_out)')).toBeDefined();
  });

  it('copies an artifact path and confirms with a toast', () => {
    render(<SubagentOverviewTab node={makeNode({ handover_state: { artifact_refs: ['reports/out.md'] } })} />);

    fireEvent.click(screen.getAllByLabelText('detailCopy')[0]);

    expect(writeText).toHaveBeenCalledWith('reports/out.md');
    expect(toast.success).toHaveBeenCalledWith('detailCopiedArtifactPath');
  });

  it('shows the verification verdict with its findings', () => {
    render(
      <SubagentOverviewTab
        node={makeNode({
          verification: {
            passed: false,
            rounds: 2,
            max_rounds: 2,
            confidence: 'high',
            findings: [{ severity: 'high', description: 'Command output missing' }],
          },
        })}
      />,
    );

    expect(screen.getByText('detailVerificationFailed')).toBeDefined();
    expect(screen.getByText('detailVerificationRounds:2/2')).toBeDefined();
    expect(screen.getByText(/Command output missing/)).toBeDefined();
  });

  it('shows the passed verdict and omits the handover card when no handover state exists', () => {
    render(
      <SubagentOverviewTab
        node={makeNode({ verification: { passed: true, rounds: 1, max_rounds: 2, confidence: 'high' } })}
      />,
    );

    expect(screen.getByText('detailVerificationPassed')).toBeDefined();
    expect(screen.queryByText('detailHandoverTitle')).toBeNull();
  });
});
