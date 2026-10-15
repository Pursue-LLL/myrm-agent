import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InSituCommentPinLayer } from '../InSituCommentPinLayer';
import { useInsituAnnotationStore } from '../useInsituAnnotationStore';
import { VisualCommentPin } from '../insituAnnotationTypes';

describe('InSituCommentPinLayer 组件单测', () => {
  const samplePins: VisualCommentPin[] = [
    {
      id: 'pin-101',
      index: 1,
      x: 150,
      y: 200,
      selector: '#cta-btn',
      targetTag: 'button',
      targetPreviewSnippet: '<button>立即购买</button>',
      commentText: '文案修改为免费试用7天',
      createdAt: '15:00:00',
    },
    {
      id: 'pin-102',
      index: 2,
      x: 300,
      y: 100,
      selector: '#logo',
      targetTag: 'img',
      targetPreviewSnippet: '<img src="logo.png" />',
      commentText: '替换为高分辨率矢量 Logo',
      createdAt: '15:01:00',
    },
  ];

  beforeEach(() => {
    useInsituAnnotationStore.setState({
      comments: samplePins,
      activeCommentId: null,
    });
  });

  it('渲染画布上的所有批注钉序号徽章', () => {
    render(<InSituCommentPinLayer />);

    expect(screen.getByTestId('insitu-comment-pin-layer')).toBeInTheDocument();
    expect(screen.getByTestId('comment-pin-badge-1')).toBeInTheDocument();
    expect(screen.getByTestId('comment-pin-badge-2')).toBeInTheDocument();
  });

  it('点击序号徽章能展开对应批注的气泡卡片并支持修改诉求内容', () => {
    render(<InSituCommentPinLayer />);

    const badge1 = screen.getByTestId('comment-pin-badge-1');
    fireEvent.click(badge1);

    expect(useInsituAnnotationStore.getState().activeCommentId).toBe('pin-101');
    expect(screen.getByTestId('comment-pin-popover-1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('文案修改为免费试用7天')).toBeInTheDocument();

    const textarea = screen.getByDisplayValue('文案修改为免费试用7天');
    fireEvent.change(textarea, { target: { value: '文案修改为立即预约试驾' } });

    expect(useInsituAnnotationStore.getState().comments[0].commentText).toBe('文案修改为立即预约试驾');
  });

  it('点击气泡内的删除按钮能移除该批注', () => {
    useInsituAnnotationStore.setState({ activeCommentId: 'pin-101' });
    render(<InSituCommentPinLayer />);

    const deleteBtn = screen.getByRole('button', { name: '删除批注' });
    fireEvent.click(deleteBtn);

    expect(useInsituAnnotationStore.getState().comments.length).toBe(1);
    expect(useInsituAnnotationStore.getState().comments[0].id).toBe('pin-102');
  });
});
