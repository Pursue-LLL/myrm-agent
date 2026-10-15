import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorkspaceScaffoldingStore } from '../useWorkspaceScaffoldingStore';
import { WorkspaceScaffoldingCard } from '../WorkspaceScaffoldingCard';
import { ScaffoldingProposal } from '../workspaceScaffoldingTypes';

describe('WorkspaceScaffoldingCard', () => {
  beforeEach(() => {
    useWorkspaceScaffoldingStore.getState().reset();
  });

  const mockProposal: ScaffoldingProposal = {
    id: 'mock-scaffold-1',
    workspacePath: '/Users/test/projects/my-client-project',
    matchedUtterance: '按四区初始化',
    status: 'pending_review',
    createdAt: Date.now(),
    moves: [
      {
        sourcePath: '/Users/test/projects/my-client-project/contract.pdf',
        fileName: 'contract.pdf',
        targetZone: '01_raw_materials',
        targetPath:
          '/Users/test/projects/my-client-project/01_raw_materials/contract.pdf',
        isReadOnly: true,
        rationale: '原始合同锁只读',
      },
      {
        sourcePath: '/Users/test/projects/my-client-project/notes.tmp',
        fileName: 'notes.tmp',
        targetZone: '02_process_drafts',
        targetPath:
          '/Users/test/projects/my-client-project/02_process_drafts/notes.tmp',
        isReadOnly: false,
        rationale: '过程草稿',
      },
    ],
    generatedDocs: [
      {
        path: '/Users/test/projects/my-client-project/AGENTS.md',
        title: 'AGENTS.md（智能体行为规约与红线手册）',
        purpose: '守则',
        draftContent: '# 规约',
      },
      {
        path: '/Users/test/projects/my-client-project/00_项目总览.md',
        title: '00_项目总览.md（动态目标与材料总览）',
        purpose: '总览',
        draftContent: '# 总览',
      },
    ],
  };

  it('renders card title, workspace path, and zone counts accurately', () => {
    useWorkspaceScaffoldingStore.setState({
      proposals: { [mockProposal.id]: mockProposal },
    });

    render(<WorkspaceScaffoldingCard proposal={mockProposal} />);

    expect(screen.getByText('标准四区规整推演方案')).toBeDefined();
    expect(
      screen.getByText(/my-client-project · 待规整文件 2 项/),
    ).toBeDefined();
    expect(screen.getByText('01 原始原件')).toBeDefined();
    expect(screen.getByText('1 份 (只读)')).toBeDefined();
    expect(screen.getByText('02 过程草稿')).toBeDefined();
    expect(screen.getByText('1 份')).toBeDefined();
  });

  it('toggles file change tree visibility when tree toggle button is clicked', () => {
    useWorkspaceScaffoldingStore.setState({
      proposals: { [mockProposal.id]: mockProposal },
    });

    render(<WorkspaceScaffoldingCard proposal={mockProposal} />);

    const toggleBtn = screen.getByText('查看拟迁移文件变动树 (2 项)');
    expect(screen.queryByText('contract.pdf')).toBeNull();

    fireEvent.click(toggleBtn);
    expect(screen.getByText('contract.pdf')).toBeDefined();
    expect(screen.getByText('➔ 01_raw_materials/')).toBeDefined();

    fireEvent.click(toggleBtn);
    expect(screen.queryByText('contract.pdf')).toBeNull();
  });

  it('triggers doc preview modal on preview button click', () => {
    useWorkspaceScaffoldingStore.setState({
      proposals: { [mockProposal.id]: mockProposal },
    });

    render(<WorkspaceScaffoldingCard proposal={mockProposal} />);

    const previewBtn = screen.getByText('AGENTS.md');
    fireEvent.click(previewBtn);

    const store = useWorkspaceScaffoldingStore.getState();
    expect(store.isPreviewModalOpen).toBe(true);
    expect(store.previewingDoc?.title).toContain('AGENTS.md');
  });

  it('handles apply button click and triggers onConfirmed callback', () => {
    useWorkspaceScaffoldingStore.setState({
      proposals: { [mockProposal.id]: mockProposal },
    });

    const onConfirmed = vi.fn();
    render(
      <WorkspaceScaffoldingCard
        proposal={mockProposal}
        onConfirmed={onConfirmed}
      />,
    );

    const applyBtn = screen.getByText('确认落盘 (Apply)');
    fireEvent.click(applyBtn);

    expect(onConfirmed).toHaveBeenCalledTimes(1);
    const store = useWorkspaceScaffoldingStore.getState();
    expect(store.proposals[mockProposal.id]?.status).toBe('confirmed');
  });

  it('handles cancel button click and triggers onCancelled callback', () => {
    useWorkspaceScaffoldingStore.setState({
      proposals: { [mockProposal.id]: mockProposal },
    });

    const onCancelled = vi.fn();
    render(
      <WorkspaceScaffoldingCard
        proposal={mockProposal}
        onCancelled={onCancelled}
      />,
    );

    const cancelBtn = screen.getByText('保持原样');
    fireEvent.click(cancelBtn);

    expect(onCancelled).toHaveBeenCalledTimes(1);
    const store = useWorkspaceScaffoldingStore.getState();
    expect(store.proposals[mockProposal.id]?.status).toBe('cancelled');
  });

  it('displays confirmed badge when proposal is confirmed', () => {
    const confirmedProposal: ScaffoldingProposal = {
      ...mockProposal,
      status: 'confirmed',
    };

    render(<WorkspaceScaffoldingCard proposal={confirmedProposal} />);

    expect(screen.getByText('已落盘生效')).toBeDefined();
    expect(screen.queryByText('确认落盘 (Apply)')).toBeNull();
  });

  it('displays cancelled badge when proposal is cancelled', () => {
    const cancelledProposal: ScaffoldingProposal = {
      ...mockProposal,
      status: 'cancelled',
    };

    render(<WorkspaceScaffoldingCard proposal={cancelledProposal} />);

    expect(screen.getByText('已取消规整')).toBeDefined();
    expect(screen.queryByText('确认落盘 (Apply)')).toBeNull();
  });
});
