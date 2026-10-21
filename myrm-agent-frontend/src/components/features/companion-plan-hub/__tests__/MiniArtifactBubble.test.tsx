import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MiniArtifactBubble } from '../MiniArtifactBubble';
import { useCompanionPlanHubStore } from '../useCompanionPlanHubStore';
import type { MiniArtifactSummary } from '../companionPlanHubTypes';

describe('MiniArtifactBubble', () => {
  const mockArtifact: MiniArtifactSummary = {
    artifactId: 'art-store-01',
    title: '店长经营看板独立单文件工件',
    summaryText: '已完成指标流聚合、异常数值沙盒校验与 Canvas 折线图构建',
    previewUrl: 'http://localhost:3000/preview/art-store-01',
    sourcePath: '/workspace/artifacts/store_dashboard.html',
    completedAt: Date.now(),
  };

  beforeEach(() => {
    useCompanionPlanHubStore.getState().resetAll();
  });

  it('未进入成果气泡模式时不渲染任何内容', () => {
    useCompanionPlanHubStore.setState({
      displayMode: 'pet_only',
      completedArtifact: null,
    });
    const { container } = render(<MiniArtifactBubble />);
    expect(container.firstChild).toBeNull();
  });

  it('进入成果气泡模式时正常渲染标题、摘要与三大快捷动作按钮', () => {
    useCompanionPlanHubStore.setState({
      displayMode: 'artifact_bubble',
      completedArtifact: mockArtifact,
    });

    render(<MiniArtifactBubble />);
    expect(screen.getByTestId('mini-artifact-bubble')).toBeInTheDocument();
    expect(
      screen.getByText('店长经营看板独立单文件工件')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('artifact-open-browser-btn')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('artifact-view-source-btn')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('artifact-open-conversation-btn')
    ).toBeInTheDocument();
  });

  it('点击浏览器打开按钮触发回调并传递 previewUrl', () => {
    const handleOpenBrowser = vi.fn();
    useCompanionPlanHubStore.setState({
      displayMode: 'artifact_bubble',
      completedArtifact: mockArtifact,
    });

    render(<MiniArtifactBubble onOpenBrowser={handleOpenBrowser} />);
    const btn = screen.getByTestId('artifact-open-browser-btn');
    fireEvent.click(btn);

    expect(handleOpenBrowser).toHaveBeenCalledWith(
      'http://localhost:3000/preview/art-store-01'
    );
  });

  it('点击查看源码按钮触发回调并传递 sourcePath', () => {
    const handleViewSource = vi.fn();
    useCompanionPlanHubStore.setState({
      displayMode: 'artifact_bubble',
      completedArtifact: mockArtifact,
    });

    render(<MiniArtifactBubble onViewSource={handleViewSource} />);
    const btn = screen.getByTestId('artifact-view-source-btn');
    fireEvent.click(btn);

    expect(handleViewSource).toHaveBeenCalledWith(
      '/workspace/artifacts/store_dashboard.html'
    );
  });

  it('点击展开对话按钮触发回调', () => {
    const handleOpenConversation = vi.fn();
    useCompanionPlanHubStore.setState({
      displayMode: 'artifact_bubble',
      completedArtifact: mockArtifact,
    });

    render(
      <MiniArtifactBubble onOpenConversation={handleOpenConversation} />
    );
    const btn = screen.getByTestId('artifact-open-conversation-btn');
    fireEvent.click(btn);

    expect(handleOpenConversation).toHaveBeenCalledTimes(1);
  });

  it('点击关闭按钮退出成果气泡模式', () => {
    const handleClose = vi.fn();
    useCompanionPlanHubStore.setState({
      displayMode: 'artifact_bubble',
      completedArtifact: mockArtifact,
    });

    render(<MiniArtifactBubble onClose={handleClose} />);
    const closeBtn = screen.getByTestId('close-artifact-bubble-btn');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(useCompanionPlanHubStore.getState().displayMode).toBe('pet_only');
  });
});
