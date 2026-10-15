import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SideChatDrawer } from '../SideChatDrawer';
import { useSideChatStore } from '../useSideChatStore';

describe('SideChatDrawer', () => {
  beforeEach(() => {
    useSideChatStore.getState().reset();
  });

  it('isOpen 为 false 时返回 null 不渲染 DOM', () => {
    useSideChatStore.setState({ isOpen: false });
    const { container } = render(<SideChatDrawer />);

    expect(container.firstChild).toBeNull();
  });

  it('打开时正常渲染主任务运行步进与空状态引导', () => {
    useSideChatStore.setState({ isOpen: true });
    render(<SideChatDrawer />);

    expect(screen.getByTestId('side-chat-drawer')).toBeInTheDocument();
    expect(screen.getByText('平行支线对话 (Side Chat)')).toBeInTheDocument();
    expect(screen.getByText(/主任务: 第 2\/5 步运行中/)).toBeInTheDocument();
    expect(screen.getByText('长任务进行中，随时发起支线交流')).toBeInTheDocument();
  });

  it('支持在输入框键入并发送支线消息', () => {
    useSideChatStore.setState({ isOpen: true });
    render(<SideChatDrawer />);

    const input = screen.getByPlaceholderText('随时补充小需求或询问进度...');
    fireEvent.change(input, { target: { value: '增加导出 Excel 功能' } });

    const submitBtn = screen.getByTitle('发送支线消息');
    fireEvent.click(submitBtn);

    expect(screen.getByText('增加导出 Excel 功能')).toBeInTheDocument();
    expect(
      screen.getByText(/已将增量需求 “增加导出 Excel 功能” 挂入非阻塞缓冲队列/)
    ).toBeInTheDocument();
    expect(screen.getByText(/已挂入缓冲队列 · 主任务在下一步平滑吸收/)).toBeInTheDocument();
  });

  it('点击快捷微调芯片直接发送', () => {
    useSideChatStore.setState({ isOpen: true });
    render(<SideChatDrawer />);

    const quickBtn = screen.getByText('询问进度');
    fireEvent.click(quickBtn);

    expect(screen.getByText('现在进行到哪一步了？')).toBeInTheDocument();
    expect(screen.getByText(/协作者即时响应 · 未中断主任务沙箱/)).toBeInTheDocument();
  });

  it('支持撤回微调条目', () => {
    useSideChatStore.setState({ isOpen: true });
    const store = useSideChatStore.getState();
    store.sendSideMessage('顺手加个多余按钮');

    render(<SideChatDrawer />);

    const dismissBtn = screen.getByTitle('撤回该微调');
    fireEvent.click(dismissBtn);

    expect(useSideChatStore.getState().steeringQueue[0]?.status).toBe('cancelled');
    expect(useSideChatStore.getState().messages[0]?.steeringStatus).toBe('discarded');
  });

  it('点击关闭按钮关闭抽屉并触发 onClose', () => {
    const handleClose = vi.fn();
    useSideChatStore.setState({ isOpen: true });

    render(<SideChatDrawer onClose={handleClose} />);

    const closeBtn = screen.getByTitle('关闭支线抽屉');
    fireEvent.click(closeBtn);

    expect(useSideChatStore.getState().isOpen).toBe(false);
    expect(handleClose).toHaveBeenCalled();
  });
});
