// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SubagentInsightsView from '../SubagentInsightsView';
import type { SubagentNode } from '@/store/chat/useSubagentStore';

// 带参数回显：既验证走了翻译键，也验证传入的插值参数正确
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

function makeNode(taskId: string, partial: Partial<SubagentNode> = {}): SubagentNode {
  return {
    task_id: taskId,
    parent_task_id: '',
    agent_type: 'researcher',
    description: 'Investigate',
    status: 'completed',
    progress: 100,
    stream: [],
    ...partial,
  };
}

describe('SubagentInsightsView', () => {
  it('shows a translated empty state when there are no visible nodes', () => {
    render(<SubagentInsightsView nodes={[makeNode('hidden', { internal: true })]} />);

    expect(screen.getByText('insightsEmpty')).toBeDefined();
  });

  it('reports a stalled node as an anomaly, offers advice, and selects it by click and keyboard', () => {
    const onSelectNode = vi.fn();
    const nodes = [makeNode('t1', { stale: true, staleDurationSeconds: 90, duration_seconds: 12 })];

    render(<SubagentInsightsView nodes={nodes} onSelectNode={onSelectNode} />);

    expect(screen.getByText('insightsAdviceTitle')).toBeDefined();
    expect(screen.getByText('insightsAdviceStalled')).toBeDefined();
    expect(screen.getByText('insightsAnomaliesTitle:{"count":1}')).toBeDefined();

    const row = screen.getByRole('button');
    expect(row.textContent).toContain('insightsAnomalyStalled:{"seconds":90}');

    fireEvent.click(row);
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(onSelectNode).toHaveBeenCalledTimes(2);
    expect(onSelectNode).toHaveBeenCalledWith('t1');
  });

  it('flags a node that ran more than twice as long as its type average', () => {
    const nodes = [
      makeNode('a', { duration_seconds: 10 }),
      makeNode('b', { duration_seconds: 10 }),
      makeNode('c', { duration_seconds: 100 }),
    ];

    render(<SubagentInsightsView nodes={nodes} />);

    expect(screen.getByRole('button').textContent).toContain(
      'insightsAnomalySlow:{"duration":100,"average":40,"type":"researcher"}',
    );
  });

  it('shows the all-clear message when nothing is anomalous', () => {
    render(<SubagentInsightsView nodes={[makeNode('a', { duration_seconds: 5 })]} />);

    expect(screen.getByText('insightsAnomaliesEmpty')).toBeDefined();
    expect(screen.queryByText('insightsAdviceTitle')).toBeNull();
  });

  it('advises pooling outputs once more than the fan-out limit of subagents run', () => {
    const nodes = Array.from({ length: 16 }, (_, i) => makeNode(`n${i}`));

    render(<SubagentInsightsView nodes={nodes} />);

    expect(screen.getByText('insightsAdviceFanOut:{"limit":15}')).toBeDefined();
    expect(screen.getByText('insightsSpawned:{"count":16}')).toBeDefined();
  });

  it('advises reviewing findings when independent verification failed', () => {
    const nodes = [makeNode('v', { verification: { passed: false, rounds: 2, max_rounds: 3, confidence: 'low' } })];

    render(<SubagentInsightsView nodes={nodes} />);

    expect(screen.getByText('insightsAdviceVerification:{"count":1}')).toBeDefined();
  });
});
