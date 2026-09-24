import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WikiConceptLinksPanel } from '../WikiConceptLinksPanel';
import { wikiService } from '@/services/wikiService';

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getConceptLinks: vi.fn(),
  },
}));

describe('WikiConceptLinksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders backlinks with context snippet and handles tab switching', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      concept_name: 'test-concept',
      outlinks: [
        {
          name: 'outgoing-target',
          weight: 3.0,
          exists: true,
          context_snippet: null,
        },
      ],
      backlinks: [
        {
          name: 'referencing-source',
          weight: 4.5,
          exists: true,
          context_snippet: 'This document references [[test-concept]] directly.',
          heading: '采购审核机制',
          line_number: 7,
        },
      ],
      ego_graph: {
        nodes: [
          { id: 'test-concept', name: 'test concept', group: 1 },
          { id: 'referencing-source', name: 'referencing source', group: 1 },
        ],
        edges: [
          { source: 'referencing-source', target: 'test-concept', weight: 4.5 },
        ],
      },
    });

    const handleSelect = vi.fn();
    render(
      <WikiConceptLinksPanel
        conceptName="test-concept"
        agentId="agent-1"
        onSelectConcept={handleSelect}
      />
    );

    // 验证标题和统计胶囊
    expect(await screen.findByText('双向链接与知识脉络')).toBeInTheDocument();
    expect(screen.getByText(/1 引用 · 1 出链/)).toBeInTheDocument();

    // 验证小节标题和行号徽章渲染
    expect(screen.getByText('§ 采购审核机制')).toBeInTheDocument();
    expect(screen.getByText('L7')).toBeInTheDocument();

    // 默认展示 Backlinks tab
    expect(screen.getByText('referencing-source')).toBeInTheDocument();
    expect(
      screen.getByText(/“This document references \[\[test-concept\]\] directly\.”/)
    ).toBeInTheDocument();

    // 点击反链项触发跳转
    const backlinkItem = screen.getByText('referencing-source');
    await userEvent.click(backlinkItem);
    expect(handleSelect).toHaveBeenCalledWith('referencing-source');

    // 切换到 Outlinks tab
    const outlinksTabBtn = screen.getByText(/引用前置/);
    await userEvent.click(outlinksTabBtn);
    expect(await screen.findByText('outgoing-target')).toBeInTheDocument();

    // 切换到 Ego Graph tab
    const egoTabBtn = screen.getByText(/局部拓扑/);
    await userEvent.click(egoTabBtn);
    expect(await screen.findByText(/局部关联网：2 节点 · 1 关系边/)).toBeInTheDocument();
  });
});
