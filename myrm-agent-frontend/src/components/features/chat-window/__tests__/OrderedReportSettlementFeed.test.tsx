'use client';

/**
 * [INPUT]: OrderedReportSettlementFeed.tsx 与 mock 队列数据
 * [OUTPUT]: 验证 Subagent Report-before-Settlement 严格保序 FIFO 队列与 Active Report Wakeup Feed 渲染及交互
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/OrderedReportSettlementFeed.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  OrderedReportSettlementFeed,
  FifoQueueEnvelopeItem,
  NamedSubagentInstanceConfigItem,
} from '../OrderedReportSettlementFeed';

const mockInstances: NamedSubagentInstanceConfigItem[] = [
  {
    instanceName: 'codex-worker-alpha',
    role: 'backend_developer',
    permissionMode: 'approve-for-me',
    reportDelivery: 'next-step',
  },
  {
    instanceName: 'test-runner-beta',
    role: 'qa_engineer',
    permissionMode: 'never',
    reportDelivery: 'quiet',
  },
];

const mockItems: FifoQueueEnvelopeItem[] = [
  {
    sequenceId: 1,
    itemType: 'report',
    taskId: 'task_sub_01',
    subagentId: 'codex-worker-alpha',
    wakesParent: true,
    timestamp: 1720000000,
    reportPayload: {
      reportId: 'rep_001',
      subagentId: 'codex-worker-alpha',
      taskId: 'task_sub_01',
      summary: 'Schema definition completed',
      content: 'Added 5 DTO models and validations.',
      deliveryMode: 'next-step',
      timestamp: 1720000000,
    },
  },
  {
    sequenceId: 2,
    itemType: 'settlement',
    taskId: 'task_sub_01',
    subagentId: 'codex-worker-alpha',
    wakesParent: true,
    timestamp: 1720000005,
    settlementPayload: {
      settlementId: 'stl_001',
      subagentId: 'codex-worker-alpha',
      taskId: 'task_sub_01',
      exitCode: 0,
      status: 'completed',
      summary: 'Worker completed execution successfully',
      timestamp: 1720000005,
    },
  },
  {
    sequenceId: 3,
    itemType: 'report',
    taskId: 'task_sub_02',
    subagentId: 'test-runner-beta',
    wakesParent: false,
    timestamp: 1720000010,
    reportPayload: {
      reportId: 'rep_002',
      subagentId: 'test-runner-beta',
      taskId: 'task_sub_02',
      summary: 'Running background suite',
      deliveryMode: 'quiet',
      timestamp: 1720000010,
    },
  },
];

describe('OrderedReportSettlementFeed', () => {
  it('renders top banner metadata with chatId and pending items count', () => {
    render(
      <OrderedReportSettlementFeed
        chatId="chat_session_fifo_01"
        instances={mockInstances}
        items={mockItems}
      />
    );

    expect(screen.getByTestId('ordered-report-settlement-feed')).toBeInTheDocument();
    expect(screen.getByTestId('feed-chat-badge')).toHaveTextContent('chat_session_fifo_01');
    expect(screen.getByTestId('pending-items-badge')).toHaveTextContent('Pending: 3 (2 rep / 1 stl)');
  });

  it('toggles subagent instances roster section on button click', () => {
    render(
      <OrderedReportSettlementFeed
        chatId="chat_session_fifo_02"
        instances={mockInstances}
        items={mockItems}
      />
    );

    expect(screen.queryByTestId('subagents-roster-section')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-instances-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('subagents-roster-section')).toBeInTheDocument();
    expect(screen.getByTestId('instance-card-codex-worker-alpha')).toHaveTextContent('codex-worker-alpha');
    expect(screen.getByTestId('instance-card-test-runner-beta')).toHaveTextContent('qa_engineer');
  });

  it('toggles ordered FIFO queue stream and renders report and settlement items', () => {
    render(
      <OrderedReportSettlementFeed
        chatId="chat_session_fifo_03"
        instances={mockInstances}
        items={mockItems}
      />
    );

    expect(screen.queryByTestId('ordered-queue-section')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-feed-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('ordered-queue-section')).toBeInTheDocument();

    // Check envelope #1 (Report)
    expect(screen.getByTestId('queue-envelope-1')).toBeInTheDocument();
    expect(screen.getByTestId('wakeup-badge-1')).toHaveTextContent('Next-Step Wakeup');
    expect(screen.getByText('Schema definition completed')).toBeInTheDocument();

    // Check envelope #2 (Settlement)
    expect(screen.getByTestId('queue-envelope-2')).toBeInTheDocument();
    expect(screen.getByText('Worker completed execution successfully')).toBeInTheDocument();

    // Check envelope #3 (Quiet report)
    expect(screen.getByTestId('queue-envelope-3')).toBeInTheDocument();
    expect(screen.getByTestId('wakeup-badge-3')).toHaveTextContent('Quiet');
  });

  it('fires onDrainBatch and onRefreshStatus callbacks upon user action', () => {
    const handleDrain = vi.fn();
    const handleRefresh = vi.fn();

    render(
      <OrderedReportSettlementFeed
        chatId="chat_session_fifo_04"
        instances={mockInstances}
        items={mockItems}
        onDrainBatch={handleDrain}
        onRefreshStatus={handleRefresh}
      />
    );

    const drainBtn = screen.getByTestId('drain-batch-btn');
    fireEvent.click(drainBtn);
    expect(handleDrain).toHaveBeenCalledWith(50);

    const refreshBtn = screen.getByTestId('refresh-status-btn');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalled();
  });

  it('renders urgent interrupt banner and item-level badge when urgent report exists', () => {
    const urgentItems: FifoQueueEnvelopeItem[] = [
      {
        sequenceId: 99,
        itemType: 'report',
        taskId: 'task_sub_crit_99',
        subagentId: 'worker-sentinel',
        wakesParent: true,
        urgentInterrupt: true,
        timestamp: 1720000099,
        reportPayload: {
          reportId: 'rep_crit_99',
          subagentId: 'worker-sentinel',
          taskId: 'task_sub_crit_99',
          summary: 'Fatal 429 rate limit reached',
          severity: 'critical',
          deliveryMode: 'next-step',
          timestamp: 1720000099,
        },
      },
    ];

    render(
      <OrderedReportSettlementFeed
        chatId="chat_session_fifo_05"
        instances={mockInstances}
        items={urgentItems}
        urgentInterrupt={true}
      />
    );

    // Top banner urgent interrupt badge
    expect(screen.getByTestId('urgent-interrupt-badge')).toBeInTheDocument();
    expect(screen.getByTestId('urgent-interrupt-badge')).toHaveTextContent('URGENT INTERRUPT');

    // Expand queue to inspect item
    fireEvent.click(screen.getByTestId('toggle-feed-btn'));
    expect(screen.getByTestId('urgent-item-badge-99')).toBeInTheDocument();
    expect(screen.getByText('Fatal 429 rate limit reached')).toBeInTheDocument();
  });

  it('renders aggregated natural-language summary rollup panel when provided', () => {
    const sampleRollup = '[codex-worker-alpha] Report: Schema definition completed | [worker-sentinel] [CRITICAL] Report: Fatal 429 rate limit reached';

    render(
      <OrderedReportSettlementFeed
        chatId="chat_session_fifo_06"
        instances={mockInstances}
        items={mockItems}
        summaryRollup={sampleRollup}
      />
    );

    expect(screen.getByTestId('summary-rollup-panel')).toBeInTheDocument();
    expect(screen.getByText('Aggregated Step Rollup Summary')).toBeInTheDocument();
    expect(screen.getByText(sampleRollup)).toBeInTheDocument();
  });
});

