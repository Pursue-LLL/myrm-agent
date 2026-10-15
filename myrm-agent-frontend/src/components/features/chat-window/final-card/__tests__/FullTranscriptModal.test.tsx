import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { FullTranscriptModal } from '../FullTranscriptModal';
import { assembleFinalCardContract } from '../finalCardEngine';
import { useFinalCardStore } from '../useFinalCardStore';

describe('FullTranscriptModal', () => {
  beforeEach(() => {
    act(() => {
      useFinalCardStore.getState().resetStore();
    });
  });

  it('renders nothing when activeTranscriptCardId is null', () => {
    const { container } = render(<FullTranscriptModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders full transcript modal when card is active', () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-modal-1',
      title: '主线执行任务',
      summary: '任务顺利完成',
      executionDurationMs: 12500,
      rawLogsPreview: [
        '2026-10-15T12:00:00.000Z [info] Starting execution',
        '2026-10-15T12:00:10.000Z [info] All checks passed',
      ],
    });

    act(() => {
      useFinalCardStore.getState().upsertCard(card);
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });

    render(<FullTranscriptModal />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('完整执行轨迹 · 主线执行任务')).toBeInTheDocument();
    expect(screen.getByText('耗时: 12.5s')).toBeInTheDocument();
    expect(screen.getByText('日志量: 2 行')).toBeInTheDocument();
    expect(screen.getByText('2026-10-15T12:00:00.000Z [info] Starting execution')).toBeInTheDocument();
    expect(screen.getByText('2026-10-15T12:00:10.000Z [info] All checks passed')).toBeInTheDocument();
  });

  it('renders placeholder when rawLogsPreview is empty', () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-empty',
      title: '空日志任务',
      summary: '无日志输出',
    });

    act(() => {
      useFinalCardStore.getState().upsertCard(card);
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });

    render(<FullTranscriptModal />);
    expect(screen.getByText('暂无精简日志预览片段')).toBeInTheDocument();
  });

  it('closes modal on close button and footer button click', () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-close',
      title: '关闭测试',
      summary: '测试关闭',
    });

    act(() => {
      useFinalCardStore.getState().upsertCard(card);
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });

    const onClose = vi.fn();
    const { rerender } = render(<FullTranscriptModal onClose={onClose} />);

    // Click close icon button
    const closeBtn = screen.getByLabelText('关闭对话框');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();

    // Reopen and test footer button
    act(() => {
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });
    rerender(<FullTranscriptModal onClose={onClose} />);

    const doneBtn = screen.getByText('完成查看');
    fireEvent.click(doneBtn);
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();
  });

  it('closes modal on Escape key press and backdrop click', () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-esc',
      title: 'Esc测试',
      summary: '测试Escape键',
    });

    act(() => {
      useFinalCardStore.getState().upsertCard(card);
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });

    render(<FullTranscriptModal />);

    // Press Escape
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();

    // Reopen and click backdrop
    act(() => {
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });

    const backdrop = screen.getByTestId('transcript-modal-backdrop');
    fireEvent.click(backdrop);
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();
  });

  it('copies logs to clipboard', async () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-copy',
      title: '复制测试',
      summary: '测试复制日志',
      rawLogsPreview: ['log line 1', 'log line 2'],
    });

    act(() => {
      useFinalCardStore.getState().upsertCard(card);
      useFinalCardStore.getState().openTranscriptModal(card.id);
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<FullTranscriptModal />);

    const copyBtn = screen.getByLabelText('复制日志');
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextMock).toHaveBeenCalledWith('log line 1\nlog line 2');
    expect(screen.getByText('已复制')).toBeInTheDocument();
  });
});
