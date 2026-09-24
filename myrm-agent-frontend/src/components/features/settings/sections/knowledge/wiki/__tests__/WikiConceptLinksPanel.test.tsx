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

  it('renders correct empty states across all tabs', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      concept_name: 'empty-concept',
      outlinks: [],
      backlinks: [],
      ego_graph: { nodes: [], edges: [] },
    });

    render(<WikiConceptLinksPanel conceptName="empty-concept" />);

    // Tab 1 (Backlinks) 默认展示空态
    expect(
      await screen.findByText('暂无上游词条或研报直接引用此知识点')
    ).toBeInTheDocument();

    // 切换 Tab 2 (Outlinks) 展示空态
    const outlinksTabBtn = screen.getByText(/引用前置/);
    await userEvent.click(outlinksTabBtn);
    expect(
      await screen.findByText('此词条尚未显式引用其他知识点')
    ).toBeInTheDocument();

    // 切换 Tab 3 (Ego Graph) 展示空态
    const egoTabBtn = screen.getByText(/局部拓扑/);
    await userEvent.click(egoTabBtn);
    expect(await screen.findByText('暂无局部拓扑数据')).toBeInTheDocument();
  });

  it('disables interaction for ghost references where exists is false', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      concept_name: 'ghost-test',
      outlinks: [
        {
          name: 'unresolved-outlink',
          weight: 1.0,
          exists: false,
          context_snippet: null,
        },
      ],
      backlinks: [
        {
          name: 'unresolved-backlink',
          weight: 2.0,
          exists: false,
          context_snippet: 'Pending creation [[ghost-test]]',
          heading: null,
          line_number: null,
        },
      ],
      ego_graph: { nodes: [], edges: [] },
    });

    const handleSelect = vi.fn();
    render(
      <WikiConceptLinksPanel
        conceptName="ghost-test"
        onSelectConcept={handleSelect}
      />
    );

    // 验证反链中的“待补充”徽章与禁用态
    expect(await screen.findByText('待补充')).toBeInTheDocument();
    const backlinkBtn = screen.getByText('unresolved-backlink').closest('button');
    expect(backlinkBtn).toBeDisabled();
    if (backlinkBtn) {
      await userEvent.click(backlinkBtn);
      expect(handleSelect).not.toHaveBeenCalled();
    }

    // 切换至出链 tab，验证“幽灵引用”徽章与禁用态
    const outlinksTabBtn = screen.getByText(/引用前置/);
    await userEvent.click(outlinksTabBtn);
    expect(await screen.findByText('幽灵引用')).toBeInTheDocument();
    const outlinkBtn = screen.getByText('unresolved-outlink').closest('button');
    expect(outlinkBtn).toBeDisabled();
    if (outlinkBtn) {
      await userEvent.click(outlinkBtn);
      expect(handleSelect).not.toHaveBeenCalled();
    }
  });

  it('handles ego graph center node vs neighbor node click interactions', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      concept_name: 'center-node',
      outlinks: [],
      backlinks: [],
      ego_graph: {
        nodes: [
          { id: 'center-node', name: 'Center Concept', group: 1 },
          { id: 'neighbor-node', name: 'Neighbor Concept', group: 1 },
        ],
        edges: [
          { source: 'center-node', target: 'neighbor-node', weight: 1.0 },
        ],
      },
    });

    const handleSelect = vi.fn();
    render(
      <WikiConceptLinksPanel
        conceptName="center-node"
        onSelectConcept={handleSelect}
      />
    );

    // 切换到局部拓扑
    const egoTabBtn = await screen.findByText(/局部拓扑/);
    await userEvent.click(egoTabBtn);

    // 点击中心节点：不应触发 onSelectConcept
    const centerBtn = screen.getByText('Center Concept');
    await userEvent.click(centerBtn);
    expect(handleSelect).not.toHaveBeenCalled();

    // 点击邻居节点：应当触发 onSelectConcept('neighbor-node')
    const neighborBtn = screen.getByText('Neighbor Concept');
    await userEvent.click(neighborBtn);
    expect(handleSelect).toHaveBeenCalledWith('neighbor-node');
  });

  it('displays error banner and supports retry on fetch failure', async () => {
    (wikiService.getConceptLinks as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('Network connection timeout'))
      .mockResolvedValueOnce({
        concept_name: 'retry-test',
        outlinks: [],
        backlinks: [],
        ego_graph: { nodes: [], edges: [] },
      });

    render(<WikiConceptLinksPanel conceptName="retry-test" />);

    // 验证错误提示展示
    expect(
      await screen.findByText('Network connection timeout')
    ).toBeInTheDocument();

    // 点击右上角刷新按钮重试
    const refreshBtn = screen.getByTitle('刷新链接拓扑');
    await userEvent.click(refreshBtn);

    // 验证重试成功后错误条消失，空态正常展示
    await waitFor(() => {
      expect(
        screen.queryByText('Network connection timeout')
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByText('暂无上游词条或研报直接引用此知识点')
    ).toBeInTheDocument();
  });
});

