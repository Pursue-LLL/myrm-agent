/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../command-center/MemoryCommandCenterPanels::ObserveSection (POS: 个人大脑指挥中心基础展示面板)
 * ../command-center/MemoryCommandCenterUnderstandSection::UnderstandSection (POS: 个人大脑指挥中心「理解」分区)
 * ../command-center/MemoryCommandCenterObservationPanels::EventList (POS: 个人大脑指挥中心的只读观测面板)
 *
 * [OUTPUT]
 * Command center section tests: 观察分区的类型与空间渲染、事件流回放入口守卫、理解分区的影响与冲突空态。
 *
 * [POS]
 * 命令中心分区渲染回归测试。验证拆分后的观察、理解分区与观测子面板能独立渲染，且仅带会话线索的事件可点击回放。
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { MemoryCommandCenterResponse, MemoryCommandTimelineEvent } from '@/services/memory/commandCenter';
import { EventList } from '../command-center/MemoryCommandCenterObservationPanels';
import { ObserveSection } from '../command-center/MemoryCommandCenterPanels';
import { UnderstandSection } from '../command-center/MemoryCommandCenterUnderstandSection';
import type { MemoryTranslation } from '../command-center/memoryCommandCenterFormat';

vi.mock('../insights/MemoryHealthDashboard', () => ({
  default: () => <div data-testid="health-dashboard" />,
}));

const t = ((key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${JSON.stringify(values)}` : key) as unknown as MemoryTranslation;

const makeEvent = (id: string, metadata: Record<string, unknown>): MemoryCommandTimelineEvent =>
  ({
    id,
    kind: 'recall',
    title: 'semantic',
    description: `description of ${id}`,
    occurred_at: '2026-04-29T08:05:00Z',
    metadata,
  }) as unknown as MemoryCommandTimelineEvent;

const makeSnapshot = (overrides: Record<string, unknown> = {}): MemoryCommandCenterResponse =>
  ({
    overview: { by_type: { semantic: 7 } },
    health: {},
    spaces: [
      { kind: 'shared', namespace: 'team/alpha', label: 'Alpha', binding_count: 2 },
      { kind: 'galaxy', namespace: 'far/away', label: '', binding_count: 0 },
    ],
    influence: [],
    conflicts: [],
    ...overrides,
  }) as unknown as MemoryCommandCenterResponse;

describe('ObserveSection', () => {
  it('renders type counts, memory spaces and the health dashboard', async () => {
    render(<ObserveSection snapshot={makeSnapshot()} liveStream={[]} t={t} />);

    expect(screen.getByText('types.semantic')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.spaceKind.shared')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.bindingCount:{"count":2}')).toBeInTheDocument();
    // unknown space kinds and unlabeled spaces fall back to the raw values
    expect(screen.getByText('galaxy')).toBeInTheDocument();
    expect(screen.getAllByText('far/away').length).toBeGreaterThan(0);
    expect(screen.getByText('commandCenter.timelineEmpty')).toBeInTheDocument();
    expect(await screen.findByTestId('health-dashboard')).toBeInTheDocument();
  });
});

describe('EventList replay entry', () => {
  it('makes only events carrying a chat id clickable', async () => {
    const user = userEvent.setup();
    const onEventClick = vi.fn();
    const withChat = makeEvent('with-chat', { chat_id: 'chat-42' });
    const withoutChat = makeEvent('without-chat', {});

    render(<EventList events={[withChat, withoutChat]} t={t} emptyLabel="empty" onEventClick={onEventClick} />);

    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toBeEnabled();
    expect(buttons[1]).toBeDisabled();

    await user.click(buttons[0]);
    expect(onEventClick).toHaveBeenCalledWith(withChat);
    expect(screen.getAllByText('commandCenter.openSessionReplay')).toHaveLength(1);
  });

  it('shows the empty label when there are no events', () => {
    render(<EventList events={[]} t={t} emptyLabel="nothing yet" />);
    expect(screen.getByText('nothing yet')).toBeInTheDocument();
  });
});

describe('UnderstandSection', () => {
  it('shows the empty states when there is no influence or conflict', () => {
    render(<UnderstandSection snapshot={makeSnapshot()} t={t} />);

    expect(screen.getByText('commandCenter.influenceTitle')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.influenceEmpty')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.conflictsTitle')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.conflictsEmpty')).toBeInTheDocument();
  });

  it('lists influence records with their reference count', () => {
    const snapshot = makeSnapshot({
      influence: [
        {
          id: 'inf-1',
          answer_preview: 'answer built from memory',
          occurred_at: '2026-04-29T08:05:00Z',
          influence_refs: [
            { memory_id: 'm1', memory_type: 'semantic', score: 0.8765, content_preview: 'fact' },
            { memory_id: 'm2', memory_type: 'mystery', content_preview: 'other' },
          ],
        },
      ],
    });
    render(<UnderstandSection snapshot={snapshot} t={t} />);

    expect(screen.queryByText('commandCenter.influenceEmpty')).toBeNull();
    expect(screen.getByText('answer built from memory')).toBeInTheDocument();
    expect(screen.getByText('commandCenter.influenceRefs:{"count":2}')).toBeInTheDocument();
    expect(screen.getByText(/types\.semantic · 0\.88/)).toBeInTheDocument();
    expect(screen.getByText('mystery')).toBeInTheDocument();
  });
});
