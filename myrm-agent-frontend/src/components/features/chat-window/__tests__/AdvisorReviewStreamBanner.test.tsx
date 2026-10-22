'use client';

/**
 * [INPUT]: AdvisorReviewStreamBanner.tsx 组件与各类 AdvisorReviewItem fixture
 * [OUTPUT]: 验证 aside/concern/blocker 三级干预渲染、blocker 熔断交互、详情折叠与历史抽屉
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/AdvisorReviewStreamBanner.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  AdvisorReviewStreamBanner,
  AdvisorReviewItem,
} from '../AdvisorReviewStreamBanner';

const mockAsideReview: AdvisorReviewItem = {
  reviewId: 'rev-001',
  stepId: 'step-01',
  interventionLevel: 'aside',
  shouldPause: false,
  reasoning: '检测到非关键参数可补充默认超时',
  proposedAction: 'fetch_user_profile(user_id="u123")',
  confidenceScore: 0.92,
  advisorModel: 'gpt-4o-mini',
  durationMs: 45,
};

const mockConcernReview: AdvisorReviewItem = {
  reviewId: 'rev-002',
  stepId: 'step-02',
  interventionLevel: 'concern',
  shouldPause: false,
  reasoning: '批量读取可能引发下游 API 速率限流',
  proposedAction: 'batch_export_all_records()',
  alternativeAction: 'batch_export_paginated(chunk_size=100)',
  confidenceScore: 0.88,
  advisorModel: 'claude-3-5-haiku',
  durationMs: 82,
};

const mockBlockerReview: AdvisorReviewItem = {
  reviewId: 'rev-003',
  stepId: 'step-03',
  interventionLevel: 'blocker',
  shouldPause: true,
  reasoning: '检测到高危递归删除生产目录命令，触发熔断阻断',
  proposedAction: 'run_bash("rm -rf /production/data")',
  alternativeAction: 'run_bash("rm -rf /tmp/scratch_dir")',
  confidenceScore: 0.99,
  advisorModel: 'deepseek-r1',
  durationMs: 120,
};

describe('AdvisorReviewStreamBanner', () => {
  it('returns null when no review and history are provided', () => {
    const { container } = render(<AdvisorReviewStreamBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders aside level banner with benign indicator and metadata', () => {
    render(<AdvisorReviewStreamBanner currentReview={mockAsideReview} />);

    expect(screen.getByTestId('advisor-review-banner')).toBeInTheDocument();
    expect(screen.getByTestId('advisor-level-badge')).toHaveTextContent('旁路提示 (Aside)');
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
    expect(screen.getByText('45ms')).toBeInTheDocument();
    expect(screen.getByText('置信度 92%')).toBeInTheDocument();
    expect(screen.getByText('fetch_user_profile(user_id="u123")')).toBeInTheDocument();
  });

  it('renders concern level banner with warning badge', () => {
    render(<AdvisorReviewStreamBanner currentReview={mockConcernReview} />);

    expect(screen.getByTestId('advisor-level-badge')).toHaveTextContent('预警关注 (Concern)');
    expect(screen.getByText('claude-3-5-haiku')).toBeInTheDocument();
  });

  it('renders blocker banner with paused alert and triggers action callbacks', () => {
    const onAccept = vi.fn();
    const onDismiss = vi.fn();

    render(
      <AdvisorReviewStreamBanner
        currentReview={mockBlockerReview}
        onAcceptIntervention={onAccept}
        onDismissIntervention={onDismiss}
      />
    );

    expect(screen.getByTestId('advisor-level-badge')).toHaveTextContent('阻断熔断 (Blocker)');
    expect(screen.getByText('主 Agent 已熔断暂停')).toBeInTheDocument();

    const acceptBtn = screen.getByTestId('accept-intervention-btn');
    fireEvent.click(acceptBtn);
    expect(onAccept).toHaveBeenCalledWith(mockBlockerReview);

    const dismissBtn = screen.getByTestId('dismiss-intervention-btn');
    fireEvent.click(dismissBtn);
    expect(onDismiss).toHaveBeenCalledWith(mockBlockerReview);
  });

  it('toggles detail section on expand button click', () => {
    render(<AdvisorReviewStreamBanner currentReview={mockConcernReview} />);

    expect(screen.queryByTestId('advisor-detail-section')).not.toBeInTheDocument();

    const expandBtn = screen.getByTestId('toggle-expand-btn');
    fireEvent.click(expandBtn);

    expect(screen.getByTestId('advisor-detail-section')).toBeInTheDocument();
    expect(screen.getByText(/批量读取可能引发下游 API 速率限流/)).toBeInTheDocument();
    expect(screen.getByText('batch_export_paginated(chunk_size=100)')).toBeInTheDocument();
    expect(screen.getByText(/步序号：step-02/)).toBeInTheDocument();
    expect(screen.getByText(/审查单号：rev-002/)).toBeInTheDocument();
  });

  it('toggles history drawer and supports clearing history', () => {
    const onClear = vi.fn();
    const historyList = [mockAsideReview, mockConcernReview, mockBlockerReview];

    render(
      <AdvisorReviewStreamBanner
        reviewHistory={historyList}
        onClearHistory={onClear}
      />
    );

    expect(screen.getByText('查看历史 (3)')).toBeInTheDocument();
    expect(screen.queryByTestId('advisor-history-section')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('toggle-history-btn'));
    expect(screen.getByTestId('advisor-history-section')).toBeInTheDocument();
    expect(screen.getByText('历次审查记录 (3)')).toBeInTheDocument();

    const clearBtn = screen.getByTestId('clear-history-btn');
    fireEvent.click(clearBtn);
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
