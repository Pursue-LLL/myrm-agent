import { describe, it, expect } from 'vitest';
import type { SubagentNode } from '@/store/chat/useSubagentStore';
import { classifyNodeStage, deriveStageTaskCounts } from '../stageTaskCount';

function mkNode(overrides: Partial<SubagentNode> & { task_id: string }): SubagentNode {
  return {
    parent_task_id: '',
    agent_type: 'general',
    description: `task-${overrides.task_id}`,
    status: 'completed',
    progress: 100,
    ...overrides,
  };
}

describe('classifyNodeStage', () => {
  it('classifies scope/plan stages correctly', () => {
    const scopeNode = mkNode({ task_id: '1', agent_type: 'scope_planner', description: 'Plan architecture' });
    expect(classifyNodeStage(scopeNode).category).toBe('scope');
  });

  it('classifies verification stages correctly', () => {
    const verifyNode = mkNode({ task_id: '2', agent_type: 'verifier', status: 'verifying' });
    expect(classifyNodeStage(verifyNode).category).toBe('verify');

    const nodeWithVerification = mkNode({
      task_id: '2b',
      agent_type: 'auditor',
      verification: { passed: true, rounds: 1, max_rounds: 3, confidence: 0.95 },
    });
    expect(classifyNodeStage(nodeWithVerification).category).toBe('verify');
  });

  it('classifies synthesize stages correctly', () => {
    const synthNode = mkNode({ task_id: '3', agent_type: 'synthesizer', description: 'Synthesize all findings' });
    expect(classifyNodeStage(synthNode).category).toBe('synthesize');
  });

  it('classifies fan-out workers correctly', () => {
    const workerNode = mkNode({ task_id: '4', parent_task_id: 'root', agent_type: 'coder_worker' });
    expect(classifyNodeStage(workerNode).category).toBe('fan_out');
  });
});

describe('deriveStageTaskCounts', () => {
  it('handles empty nodes gracefully', () => {
    const summary = deriveStageTaskCounts({});
    expect(summary.totalTasks).toBe(0);
    expect(summary.stages).toEqual([]);
    expect(summary.hasBlockers).toBe(false);
  });

  it('computes stage counts and upstream blocker indicators accurately', () => {
    const nodes: Record<string, SubagentNode> = {
      '1': mkNode({ task_id: '1', agent_type: 'scope', status: 'completed' }),
      '2': mkNode({ task_id: '2', parent_task_id: '1', agent_type: 'worker', status: 'running' }),
      '3': mkNode({ task_id: '3', agent_type: 'verifier', status: 'pending' }),
      '4': mkNode({ task_id: '4', agent_type: 'synthesize', status: 'pending' }),
    };

    const summary = deriveStageTaskCounts(nodes);
    expect(summary.totalTasks).toBe(4);
    expect(summary.stages.length).toBe(4);

    const scopeStage = summary.stages.find((s) => s.category === 'scope');
    expect(scopeStage?.isComplete).toBe(true);
    expect(scopeStage?.completed).toBe(1);

    const fanOutStage = summary.stages.find((s) => s.category === 'fan_out');
    expect(fanOutStage?.running).toBe(1);
    expect(fanOutStage?.isComplete).toBe(false);

    const verifyStage = summary.stages.find((s) => s.category === 'verify');
    expect(verifyStage?.isBlocked).toBe(true);
    expect(verifyStage?.waitingOnStage).toBe('fan-out');

    const synthStage = summary.stages.find((s) => s.category === 'synthesize');
    expect(synthStage?.isBlocked).toBe(true);
  });
});
