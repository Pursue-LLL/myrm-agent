import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { SpeculativeEarlyAckCard } from '../SpeculativeEarlyAckCard';
import { useTtftDecouplingStore } from '../useTtftDecouplingStore';
import { SpeculativeAckPayload } from '../ttftDecouplingTypes';

describe('SpeculativeEarlyAckCard', () => {
  const baseAck: SpeculativeAckPayload = {
    id: 'ack-test-1',
    messageId: 'msg-001',
    status: 'intent_analyzed',
    intentSummary: '正在解析多智能体编排与全双工数据总线...',
    speculativeTools: ['vector_search', 'python_repl'],
    ackTimestamp: Date.now() - 160,
    elapsedMs: 160,
  };

  beforeEach(() => {
    useTtftDecouplingStore.getState().reset();
    useTtftDecouplingStore.setState({
      activeAcks: {
        'ack-test-1': baseAck,
      },
    });
  });

  it('renders card title, latency badge, intent summary, and tools', () => {
    render(<SpeculativeEarlyAckCard ack={baseAck} />);

    expect(screen.getByTestId('speculative-ack-ack-test-1')).toBeInTheDocument();
    expect(screen.getByText('即时握手确认 (Speculative Ack)')).toBeInTheDocument();
    expect(screen.getByText('TTFT 解耦: 160ms')).toBeInTheDocument();
    expect(
      screen.getByText('正在解析多智能体编排与全双工数据总线...'),
    ).toBeInTheDocument();
    expect(screen.getByText('vector_search')).toBeInTheDocument();
    expect(screen.getByText('python_repl')).toBeInTheDocument();
    expect(screen.getByText('意图骨架已锁定')).toBeInTheDocument();
  });

  it('dismisses ack card when user clicks close button', () => {
    render(<SpeculativeEarlyAckCard ack={baseAck} />);

    const closeBtn = screen.getByRole('button', { name: '关闭即时握手卡片' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(
      useTtftDecouplingStore.getState().activeAcks['ack-test-1'],
    ).toBeUndefined();
  });
});
