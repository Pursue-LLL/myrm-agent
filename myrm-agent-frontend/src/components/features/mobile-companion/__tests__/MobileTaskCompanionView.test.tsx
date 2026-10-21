import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MobileTaskCompanionView } from '../MobileTaskCompanionView';
import { useMobileCompanionStore } from '../useMobileCompanionStore';
import { CompanionArtifact } from '../mobileCompanionTypes';

describe('MobileTaskCompanionView', () => {
  beforeEach(() => {
    useMobileCompanionStore.setState({
      activeTask: null,
      isConnected: false,
      isRemoteSteeringOpen: false,
    });
  });

  it('renders empty fallback view when no active task', () => {
    render(<MobileTaskCompanionView />);
    expect(screen.getByTestId('mobile-task-companion-view')).toBeInTheDocument();
    expect(screen.getByText('暂无活跃的长任务会话')).toBeInTheDocument();
    expect(screen.getByText('请在电脑端启动任务并扫码配对')).toBeInTheDocument();
  });

  it('renders full companion view with task progress and live indicators', () => {
    useMobileCompanionStore.setState({
      isConnected: true,
      activeTask: {
        sessionId: 'session-abcdef123456',
        taskName: '千万级全栈工程自动化重构',
        phase: 'generating',
        progress: 72,
        estimatedSecondsRemaining: 240,
        startedAt: Date.now(),
        highSnrSummary: [
          '已完成核心 AST 解析与符号提取',
          '通过端到端类型校验门禁',
        ],
        artifacts: [],
      },
    });

    render(<MobileTaskCompanionView />);
    expect(screen.getByText('随行任务看板')).toBeInTheDocument();
    expect(screen.getByText('Session: 123456')).toBeInTheDocument();
    expect(screen.getByText('实时同步中')).toBeInTheDocument();
    expect(screen.getByText('千万级全栈工程自动化重构')).toBeInTheDocument();
    expect(screen.getByText('完成度: 72%')).toBeInTheDocument();
    expect(screen.getByText(/约 4 分钟/)).toBeInTheDocument();
    expect(screen.getByText('已完成核心 AST 解析与符号提取')).toBeInTheDocument();
  });

  it('renders screenshot and artifacts with download action', () => {
    const onDownloadMock = vi.fn();
    const mockArtifact: CompanionArtifact = {
      id: 'art-1',
      name: 'refactored_bundle.zip',
      type: 'bundle',
      size: 1048576,
      downloadUrl: 'https://download.example.com/bundle.zip',
    };

    useMobileCompanionStore.setState({
      isConnected: true,
      activeTask: {
        sessionId: 'session-abcdef123456',
        taskName: '前端渲染截屏验证',
        phase: 'generating',
        progress: 88,
        estimatedSecondsRemaining: 60,
        startedAt: Date.now(),
        highSnrSummary: ['截屏生成完毕'],
        latestScreenshot: {
          id: 'shot-1',
          url: 'https://cdn.example.com/shot.png',
          title: 'Chrome Headless 渲染预览',
          timestamp: Date.now(),
        },
        artifacts: [mockArtifact],
      },
    });

    render(<MobileTaskCompanionView onDownloadArtifact={onDownloadMock} />);
    expect(screen.getByText('沙箱最新网页渲染截屏')).toBeInTheDocument();
    expect(screen.getByText('Chrome Headless 渲染预览')).toBeInTheDocument();
    expect(screen.getByAltText('Chrome Headless 渲染预览')).toBeInTheDocument();

    expect(screen.getByText('已生成工件交付物 (1)')).toBeInTheDocument();
    expect(screen.getByText('refactored_bundle.zip')).toBeInTheDocument();
    expect(screen.getByText('1024.0 KB')).toBeInTheDocument();

    const downloadBtn = screen.getByTitle('下载 refactored_bundle.zip');
    fireEvent.click(downloadBtn);
    expect(onDownloadMock).toHaveBeenCalledWith(mockArtifact);
  });
});
