// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

  it('renders Viewport tab button and switches to Viewport tab when clicked', () => {
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

    fireEvent.click(viewportTabBtn);

    expect(screen.getByTestId('subagent-viewport-active')).toBeDefined();
    expect(screen.getByText('https://docs.anthropic.com')).toBeDefined();
  });
});
