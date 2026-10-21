import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BusinessMessageCard } from '../BusinessMessageCard';
import { useDualTrackStore } from '../useDualTrackStore';
import type { TurnMessageItem } from '../dualTrackTypes';

describe('BusinessMessageCard', () => {
  const mockMessage: TurnMessageItem = {
    id: 'turn-msg-1',
    role: 'assistant',
    kind: 'business_summary',
    content: '经营分析看板已就绪',
    businessCardData: {
      title: '店长端经营看板构建方案',
      summary: '针对客单价与动销率的业务指标看板已顺利生成。',
      planSteps: ['1. 梳理数据流', '2. 构建 Canvas 交互图表'],
      artifactId: 'artifact-dash-01',
    },
    traceDetails: {
      turnId: 'turn-msg-1',
      toolCalls: [
        { id: 'c1', toolName: 'bash', inputSummary: 'python test.py' },
      ],
      codeDiffs: [
        {
          filePath: 'src/app.tsx',
          diffText: '+const a = 1;',
          additions: 10,
          deletions: 2,
        },
      ],
      terminalLogs: ['Build complete'],
      testAssertions: [{ id: 'a1', testName: 'verify', passed: true }],
      timestamp: Date.now(),
    },
    timestamp: Date.now(),
  };

  beforeEach(() => {
    useDualTrackStore.getState().resetAll();
  });

  it('正常渲染卡片标题、业务总结正文与落地步骤清单', () => {
    render(<BusinessMessageCard message={mockMessage} />);
    expect(
      screen.getByTestId('business-message-card-turn-msg-1')
    ).toBeInTheDocument();
    expect(
      screen.getByText('店长端经营看板构建方案')
    ).toBeInTheDocument();
    expect(screen.getByTestId('business-summary-text')).toHaveTextContent(
      '针对客单价与动销率的业务指标看板已顺利生成。'
    );
    expect(
      screen.getByTestId('business-plan-steps-deck')
    ).toBeInTheDocument();
    expect(screen.getByText('1. 梳理数据流')).toBeInTheDocument();
    expect(screen.getByText('2. 构建 Canvas 交互图表')).toBeInTheDocument();
  });

  it('点击查看底层代码与执行细节按钮打开工程抽屉', () => {
    const handleOpenTrace = vi.fn();
    render(
      <BusinessMessageCard
        message={mockMessage}
        onOpenTrace={handleOpenTrace}
      />
    );

    const inspectBtn = screen.getByTestId('inspect-engineering-trace-btn');
    expect(inspectBtn).toBeInTheDocument();

    fireEvent.click(inspectBtn);
    expect(handleOpenTrace).toHaveBeenCalledTimes(1);
    expect(useDualTrackStore.getState().isTraceDrawerOpen).toBe(true);
    expect(useDualTrackStore.getState().activeTraceDetails?.turnId).toBe(
      'turn-msg-1'
    );
  });

  it('点击直接打开交互工件按钮触发回调', () => {
    const handleInspectArtifact = vi.fn();
    render(
      <BusinessMessageCard
        message={mockMessage}
        onInspectArtifact={handleInspectArtifact}
      />
    );

    const artifactBtn = screen.getByTestId('inspect-artifact-btn');
    fireEvent.click(artifactBtn);
    expect(handleInspectArtifact).toHaveBeenCalledWith('artifact-dash-01');
  });
});
