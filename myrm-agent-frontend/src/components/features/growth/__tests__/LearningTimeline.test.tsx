/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LearningTimeline from '../LearningTimeline';
import type { LearningTimelineItem, LearningTimelineResponse } from '@/services/statistics';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join(',')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mocks = vi.hoisted(() => ({
  getLearningTimeline: vi.fn(),
  updateTimelineMemory: vi.fn(),
  deleteTimelineMemory: vi.fn(),
  archiveTimelineSkill: vi.fn(),
  restoreMemory: vi.fn(),
  showApiError: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  agentStore: { agents: [{ id: 'agent-1', name: 'Writer' }], fetchAgents: vi.fn() },
}));

vi.mock('@/services/statistics', () => ({
  getLearningTimeline: mocks.getLearningTimeline,
  updateTimelineMemory: mocks.updateTimelineMemory,
  deleteTimelineMemory: mocks.deleteTimelineMemory,
  archiveTimelineSkill: mocks.archiveTimelineSkill,
}));
vi.mock('@/services/memory', () => ({ restoreMemory: mocks.restoreMemory }));
vi.mock('@/lib/api', () => ({ showApiError: mocks.showApiError }));
vi.mock('@/store/useAgentStore', () => ({
  default: (selector: (state: typeof mocks.agentStore) => unknown) => selector(mocks.agentStore),
}));
vi.mock('sonner', () => ({ toast: { success: mocks.toastSuccess, error: mocks.toastError } }));

const memoryNode = (
  id: string,
  memoryType: string,
  overrides: Partial<LearningTimelineItem> = {},
): LearningTimelineItem => ({
  id,
  kind: 'fact_memory',
  title: 'Factual Knowledge',
  content: `content ${id}`,
  created_at: '2026-10-01T00:00:00+00:00',
  agent_id: null,
  confidence: 1,
  importance: 0.5,
  is_user_protected: false,
  source_chat_id: null,
  status: 'active',
  metadata: { memory_type: memoryType },
  ...overrides,
});

const skillNode = (archived: boolean, pinned = false): LearningTimelineItem => ({
  ...memoryNode('case-1', ''),
  kind: 'skill_evolution',
  title: 'demo-skill',
  content: 'improved lint detection',
  status: 'APPROVED',
  metadata: { skill_name: 'demo-skill', manageable: true, archived, pinned },
});

const page = (items: LearningTimelineItem[]): LearningTimelineResponse => ({
  items,
  total_count: items.length,
  has_more: false,
  next_cursor: null,
});

describe('LearningTimeline governance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('mutates memories with the type the server attached to the node', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([memoryNode('mem-1', 'semantic')]));
    mocks.updateTimelineMemory.mockResolvedValue({});
    render(<LearningTimeline />);

    fireEvent.click(await screen.findByTitle('editMemory'));
    expect(screen.queryByText('userProtectedBadge')).toBeNull();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'edited' } });
    fireEvent.click(screen.getByText('saveChanges'));

    await waitFor(() =>
      expect(mocks.updateTimelineMemory).toHaveBeenCalledWith('semantic', 'mem-1', {
        content: 'edited',
        importance: undefined,
        reasoning: undefined,
      }),
    );
    expect(await screen.findByText('edited')).toBeTruthy();
    // The server pins every edited memory, so the node shows the same protection a reload would.
    expect(screen.getByText('userProtectedBadge')).toBeTruthy();
  });

  it('keeps the stored importance on a content-only edit and submits it once the slider moves', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([memoryNode('mem-1', 'semantic', { importance: 0.86 })]));
    mocks.updateTimelineMemory.mockResolvedValue({});
    render(<LearningTimeline />);

    fireEvent.click(await screen.findByTitle('editMemory'));
    fireEvent.change(screen.getByLabelText('contentLabel'), { target: { value: 'typo fixed' } });
    fireEvent.click(screen.getByText('saveChanges'));
    await waitFor(() =>
      expect(mocks.updateTimelineMemory).toHaveBeenLastCalledWith('semantic', 'mem-1', {
        content: 'typo fixed',
        importance: undefined,
        reasoning: undefined,
      }),
    );

    fireEvent.click(await screen.findByTitle('editMemory'));
    fireEvent.change(screen.getByLabelText('importanceLabel'), { target: { value: '3' } });
    fireEvent.click(screen.getByText('saveChanges'));
    await waitFor(() =>
      expect(mocks.updateTimelineMemory).toHaveBeenLastCalledWith('semantic', 'mem-1', {
        content: 'typo fixed',
        importance: 0.3,
        reasoning: undefined,
      }),
    );
  });

  it('shows no importance for procedural rules, which carry none', async () => {
    mocks.getLearningTimeline.mockResolvedValue(
      page([
        memoryNode('rule-1', 'procedural', { kind: 'procedural_memory', title: 'When X', is_user_protected: true }),
      ]),
    );
    mocks.updateTimelineMemory.mockResolvedValue({});
    render(<LearningTimeline />);

    expect(await screen.findByText('userProtectedBadge')).toBeTruthy();
    expect(screen.queryByText(/^importanceValue/)).toBeNull();

    fireEvent.click(screen.getByTitle('editMemory'));
    expect(screen.queryByLabelText('importanceLabel')).toBeNull();
    fireEvent.change(screen.getByLabelText('reasoningLabel'), { target: { value: 'because' } });
    fireEvent.click(screen.getByText('saveChanges'));
    await waitFor(() =>
      expect(mocks.updateTimelineMemory).toHaveBeenCalledWith('procedural', 'rule-1', {
        content: 'content rule-1',
        importance: undefined,
        reasoning: 'because',
      }),
    );
  });

  it('shows the agent name, never the raw id, and links to the source conversation', async () => {
    mocks.getLearningTimeline.mockResolvedValue(
      page([
        memoryNode('mem-1', 'semantic', { agent_id: 'agent-1', source_chat_id: 'chat-9' }),
        memoryNode('mem-2', 'semantic', { agent_id: 'deleted-agent' }),
      ]),
    );
    render(<LearningTimeline />);

    expect(await screen.findByText('agentOrigin:Writer')).toBeTruthy();
    expect(screen.queryByText(/deleted-agent/)).toBeNull();
    expect(screen.getAllByTitle('viewSourceChat')).toHaveLength(1);
    expect(screen.getByTitle('viewSourceChat').getAttribute('href')).toBe('/chat-9');
  });

  it('flags user-protected memories of every kind', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([memoryNode('mem-1', 'semantic', { is_user_protected: true })]));
    render(<LearningTimeline />);

    expect(await screen.findByText('userProtectedBadge')).toBeTruthy();
  });

  it('asks for confirmation, removes optimistically and offers undo through the trash', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([memoryNode('mem-1', 'semantic')]));
    mocks.deleteTimelineMemory.mockResolvedValue({ deleted: true, memory_id: 'mem-1', soft_delete: true });
    mocks.restoreMemory.mockResolvedValue({});
    render(<LearningTimeline />);

    fireEvent.click(await screen.findByTitle('deleteMemory'));
    expect(mocks.deleteTimelineMemory).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('confirm'));

    await waitFor(() => expect(mocks.deleteTimelineMemory).toHaveBeenCalledWith('mem-1', 'semantic'));
    await waitFor(() => expect(screen.queryByText('content mem-1')).toBeNull());

    const options = mocks.toastSuccess.mock.calls[0][1] as { action: { onClick: () => void } };
    await act(async () => options.action.onClick());
    await waitFor(() => expect(mocks.restoreMemory).toHaveBeenCalledWith('mem-1'));
    expect(await screen.findByText('content mem-1')).toBeTruthy();
  });

  it('rolls the node back when deletion fails', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([memoryNode('mem-1', 'semantic')]));
    mocks.deleteTimelineMemory.mockRejectedValue(new Error('boom'));
    render(<LearningTimeline />);

    fireEvent.click(await screen.findByTitle('deleteMemory'));
    fireEvent.click(screen.getByText('confirm'));

    await waitFor(() => expect(mocks.showApiError).toHaveBeenCalled());
    expect(await screen.findByText('content mem-1')).toBeTruthy();
  });

  it('archives a skill by name and reverts the badge state on failure', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([skillNode(false)]));
    mocks.archiveTimelineSkill.mockRejectedValue(new Error('conflict'));
    render(<LearningTimeline />);

    fireEvent.click(await screen.findByTitle('archiveSkill'));
    fireEvent.click(screen.getByText('confirm'));

    await waitFor(() => expect(mocks.archiveTimelineSkill).toHaveBeenCalledWith('demo-skill', false));
    await waitFor(() => expect(mocks.showApiError).toHaveBeenCalled());
    expect(await screen.findByTitle('archiveSkill')).toBeTruthy();
  });

  it('does not offer archive for a pinned skill', async () => {
    mocks.getLearningTimeline.mockResolvedValue(page([skillNode(false, true)]));
    render(<LearningTimeline />);

    const button = (await screen.findByTitle('pinnedHint')) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('ignores a slow response that was superseded by a newer filter', async () => {
    let resolveFirst: (value: LearningTimelineResponse) => void = () => undefined;
    mocks.getLearningTimeline
      .mockImplementationOnce(() => new Promise<LearningTimelineResponse>((resolve) => (resolveFirst = resolve)))
      .mockResolvedValue(page([memoryNode('fresh', 'semantic')]));
    render(<LearningTimeline />);

    fireEvent.click(screen.getByText('filterFact'));
    expect(await screen.findByText('content fresh')).toBeTruthy();

    await act(async () => resolveFirst(page([memoryNode('stale', 'semantic')])));
    expect(screen.queryByText('content stale')).toBeNull();
  });
});
