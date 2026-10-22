// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SubagentDetailDrawer from '../SubagentDetailDrawer';
import type { SubagentNode } from '@/store/chat/useSubagentStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => {
  const dummy = vi.fn();
  return {
    toast: Object.assign(dummy, {
      info: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      promise: vi.fn(),
      loading: vi.fn(),
      dismiss: vi.fn(),
      message: vi.fn(),
    }),
  };
});

function makeNode(partial: Partial<SubagentNode>): SubagentNode {
  return {
    task_id: 'subtask-12345678',
    parent_task_id: '',
    agent_type: 'researcher',
    description: 'Investigate documentation',
    status: 'running',
    progress: 30,
    stream: [],
    ...partial,
  };
}

describe('SubagentDetailDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders header, tabs and overview copy through translation keys', () => {
    render(
      <SubagentDetailDrawer node={makeNode({ agent_type: '', description: '' })} open={true} onOpenChange={vi.fn()} />,
    );

    for (const key of [
      'detailFallbackAgentType',
      'detailNoDescription',
      'statusLabel.running',
      'detailDuration',
      'detailTokens',
      'detailCost',
      'detailModelInherited',
      'detailTabOverview',
      'detailTabJournal',
      'detailTabTools',
      'detailTabMessages',
      'detailTabReplay',
      'detailTabViewport',
      'detailTaskSpec',
      'detailMetadata',
      'detailRootTask',
      'detailStandardLeaf',
    ]) {
      expect(screen.getByText(key)).toBeDefined();
    }
    expect(screen.getByLabelText('detailCopy')).toBeDefined();
  });

  it('shows translated empty states for the journal, tools, messages and replay tabs', async () => {
    const user = userEvent.setup();
    render(<SubagentDetailDrawer node={makeNode({})} open={true} onOpenChange={vi.fn()} />);

    const emptyStateByTab: Array<[string, string]> = [
      ['detailTabJournal', 'detailJournalEmpty'],
      ['detailTabTools', 'detailToolsEmpty'],
      ['detailTabMessages', 'detailMessagesEmpty'],
      ['detailTabReplay', 'detailReplayEmpty'],
    ];
    for (const [tabKey, emptyKey] of emptyStateByTab) {
      await user.click(screen.getByText(tabKey));
      expect(screen.getByText(emptyKey)).toBeDefined();
    }
  });

  it('exposes the tabs as a tablist whose strip scrolls instead of wrapping or clipping on narrow screens', async () => {
    const user = userEvent.setup();
    render(<SubagentDetailDrawer node={makeNode({})} open={true} onOpenChange={vi.fn()} />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(6);
    expect(screen.getByRole('tablist').className).toContain('overflow-x-auto');
    for (const tab of tabs) {
      expect(tab.className).toContain('shrink-0');
      expect(tab.className).toContain('whitespace-nowrap');
    }

    expect(screen.getByRole('tab', { name: 'detailTabOverview' }).getAttribute('aria-selected')).toBe('true');
    await user.click(screen.getByRole('tab', { name: 'detailTabReplay' }));
    expect(screen.getByRole('tab', { name: 'detailTabReplay' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: 'detailTabOverview' }).getAttribute('aria-selected')).toBe('false');
  });

  it('wires each tab to its panel and moves between tabs with the arrow, Home and End keys', async () => {
    const user = userEvent.setup();
    render(<SubagentDetailDrawer node={makeNode({})} open={true} onOpenChange={vi.fn()} />);

    const overview = screen.getByRole('tab', { name: 'detailTabOverview' });
    const panel = screen.getByRole('tabpanel');
    expect(overview.getAttribute('aria-controls')).toBe(panel.id);
    expect(panel.getAttribute('aria-labelledby')).toBe(overview.id);
    expect(panel.getAttribute('tabindex')).toBe('0');
    const tabStops = () => screen.getAllByRole('tab').map((tab) => tab.getAttribute('tabindex'));

    act(() => overview.focus());
    expect(tabStops()).toEqual(['0', '-1', '-1', '-1', '-1', '-1']);
    await user.keyboard('{ArrowRight}');
    const journal = screen.getByRole('tab', { name: 'detailTabJournal' });
    expect(document.activeElement).toBe(journal);
    expect(tabStops()).toEqual(['-1', '0', '-1', '-1', '-1', '-1']);
    expect(journal.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(journal.id);

    await user.keyboard('{End}');
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'detailTabViewport' }));
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(overview);
    expect(overview.getAttribute('aria-selected')).toBe('true');
    await user.keyboard('{ArrowLeft}');
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: 'detailTabViewport' }));
    await user.keyboard('{Home}');
    expect(document.activeElement).toBe(overview);
  });

  it('renders Viewport tab button and switches to Viewport tab when clicked', async () => {
    const user = userEvent.setup();
    const node = makeNode({
      stream: [
        {
          kind: 'tool',
          text: JSON.stringify({
            url: 'https://docs.anthropic.com',
            title: 'Anthropic Docs',
            screenshot_base64: 'base64_sample_img_data_1234567890',
          }),
          timestamp: Date.now(),
        },
      ],
    });

    render(<SubagentDetailDrawer node={node} open={true} onOpenChange={vi.fn()} chatId="c1" />);

    const viewportTabBtn = screen.getByTestId('subagent-drawer-tab-viewport');
    expect(viewportTabBtn).toBeDefined();

    await user.click(viewportTabBtn);

    expect(screen.getByTestId('subagent-viewport-active')).toBeDefined();
    expect(screen.getByText('https://docs.anthropic.com')).toBeDefined();
  });

  it('shows the raw error diagnostic for a failed node', () => {
    render(
      <SubagentDetailDrawer
        node={makeNode({ status: 'failed', error: 'Tool call timed out' })}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText('detailErrorDiagnostic')).toBeDefined();
    expect(screen.getByText('Tool call timed out')).toBeDefined();
    expect(screen.queryByText('detailBlockedNote')).toBeNull();
  });

  it('explains a blocked node as needing review instead of printing the framework error', () => {
    render(
      <SubagentDetailDrawer
        node={makeNode({ status: 'blocked', error: 'Verifier produced no conclusive verdict' })}
        open={true}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText('detailBlockedNote')).toBeDefined();
    expect(screen.queryByText('detailErrorDiagnostic')).toBeNull();
    expect(screen.queryByText('Verifier produced no conclusive verdict')).toBeNull();
  });
});
