import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TurnOriginBadge } from '../TurnOriginBadge';
import { useTurnLineageStore } from '../useTurnLineageStore';
import { TurnProvenanceMeta } from '../turnLineageTypes';

describe('TurnOriginBadge', () => {
  const dummyCronProvenance: TurnProvenanceMeta = {
    originType: 'cron_job',
    originRefId: 'cron:daily_maintenance',
    triggerSourceTitle: '每日凌晨定时运维自检',
    executedByAgent: 'Daemon-Agent',
    timestamp: '03:00:00',
    details: { schedule: '0 3 * * *' },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useTurnLineageStore.getState().resetStore();
  });

  it('应正确渲染 Cron 触发源徽标与文本', () => {
    render(
      <TurnOriginBadge
        turnId="turn-test-1"
        provenance={dummyCronProvenance}
      />
    );

    expect(screen.getByTestId('turn-origin-badge')).toBeInTheDocument();
    expect(screen.getByText(/Cron: daily_maintenance/)).toBeInTheDocument();
  });

  it('鼠标悬停应展开 TurnProvenanceHoverCard 详述卡片，移出后隐藏', () => {
    render(
      <TurnOriginBadge
        turnId="turn-test-1"
        provenance={dummyCronProvenance}
        tokensUsed={340}
        durationMs={850}
      />
    );

    const badgeContainer = screen.getByTestId('turn-origin-badge').parentElement;
    expect(badgeContainer).not.toBeNull();
    if (badgeContainer) {
      fireEvent.mouseEnter(badgeContainer);
    }

    expect(screen.getByTestId('turn-provenance-hover-card')).toBeInTheDocument();
    expect(screen.getByText(/每日凌晨定时运维自检/)).toBeInTheDocument();
    expect(screen.getByText(/执行者: Daemon-Agent/)).toBeInTheDocument();
    expect(screen.getByText(/Token: 340 T/)).toBeInTheDocument();

    if (badgeContainer) {
      fireEvent.mouseLeave(badgeContainer);
    }
    expect(screen.queryByTestId('turn-provenance-hover-card')).not.toBeInTheDocument();
  });

  it('点击徽标能触发 selectTurn 选中该轮次', () => {
    render(
      <TurnOriginBadge
        turnId="turn-test-1"
        provenance={dummyCronProvenance}
      />
    );

    const badgeBtn = screen.getByTestId('turn-origin-badge');
    fireEvent.click(badgeBtn);

    expect(useTurnLineageStore.getState().activeTurnId).toBe('turn-test-1');
  });

  it('在 isCompact 模式下应展示精简大类标签', () => {
    render(
      <TurnOriginBadge
        turnId="turn-test-1"
        provenance={dummyCronProvenance}
        isCompact={true}
      />
    );

    expect(screen.getByText('定时调度任务')).toBeInTheDocument();
  });
});
