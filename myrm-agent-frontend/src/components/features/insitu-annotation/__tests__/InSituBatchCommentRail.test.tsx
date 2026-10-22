import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InSituBatchCommentRail } from '../InSituBatchCommentRail';
import { useInsituAnnotationStore } from '../useInsituAnnotationStore';
import { VisualCommentPin, ElementStylePatch } from '../insituAnnotationTypes';

describe('InSituBatchCommentRail 组件单测', () => {
  const sampleComments: VisualCommentPin[] = [
    {
      id: 'pin-1',
      index: 1,
      x: 100,
      y: 100,
      selector: '#header-nav',
      targetTag: 'nav',
      targetPreviewSnippet: '<nav>菜单</nav>',
      commentText: '添加半透明毛玻璃背景',
      createdAt: '10:00:00',
    },
  ];

  const samplePatches: ElementStylePatch[] = [
    {
      selector: '#btn-buy',
      tagName: 'button',
      color: '#ffffff',
      backgroundColor: '#4f46e5',
      textContent: '立即购买',
    },
  ];

  beforeEach(() => {
    useInsituAnnotationStore.setState({
      artifactId: 'art-ecommerce',
      isRailOpen: true,
      comments: sampleComments,
      stylePatches: samplePatches,
      activeCommentId: null,
    });
  });

  it('当 isRailOpen 为 false 时不渲染任何侧栏内容', () => {
    useInsituAnnotationStore.setState({ isRailOpen: false });
    const { container } = render(<InSituBatchCommentRail />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('insitu-batch-comment-rail')).not.toBeInTheDocument();
  });

  it('当 isRailOpen 为 true 时完整呈现修改清单、批注项与就地补丁项', () => {
    render(<InSituBatchCommentRail />);

    expect(screen.getByTestId('insitu-batch-comment-rail')).toBeInTheDocument();
    expect(screen.getByText('批注与修改清单')).toBeInTheDocument();
    expect(screen.getByText('2 项')).toBeInTheDocument();
    expect(screen.getByText(/添加半透明毛玻璃背景/)).toBeInTheDocument();
    expect(screen.getByText('#btn-buy')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /打包提交全部批注/ })).toBeInTheDocument();
  });

  it('点击「打包提交全部批注」能触发 onBatchDispatch 回调并附带结构化指令', () => {
    const handleDispatch = vi.fn();
    render(<InSituBatchCommentRail onBatchDispatch={handleDispatch} />);

    const dispatchBtn = screen.getByRole('button', { name: /打包提交全部批注/ });
    fireEvent.click(dispatchBtn);

    expect(handleDispatch).toHaveBeenCalledTimes(1);
    const passedPayload = handleDispatch.mock.calls[0][0];
    expect(passedPayload.artifactId).toBe('art-ecommerce');
    expect(passedPayload.totalComments).toBe(1);
    expect(passedPayload.appliedStylePatches.length).toBe(1);
    expect(passedPayload.compiledPromptInstruction).toContain('【工件画布多点精准修改需求包】');
    expect(passedPayload.compiledPromptInstruction).toContain('添加半透明毛玻璃背景');
  });

  it('支持删除单条批注与撤销单条样式补丁', () => {
    render(<InSituBatchCommentRail />);

    const deleteCommentBtn = screen.getByRole('button', { name: '删除' });
    fireEvent.click(deleteCommentBtn);
    expect(useInsituAnnotationStore.getState().comments.length).toBe(0);

    const deletePatchBtn = screen.getByRole('button', { name: '撤销补丁' });
    fireEvent.click(deletePatchBtn);
    expect(useInsituAnnotationStore.getState().stylePatches.length).toBe(0);
  });
});
