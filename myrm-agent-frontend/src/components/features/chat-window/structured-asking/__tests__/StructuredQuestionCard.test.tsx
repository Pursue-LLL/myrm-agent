import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StructuredQuestionCard } from '../StructuredQuestionCard';
import { useStructuredAskingStore } from '../useStructuredAskingStore';
import type { StructuredQuestionPayload } from '../structuredAskingTypes';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

const sampleSinglePayload: StructuredQuestionPayload = {
  questionId: 'q_db_type',
  question: '请选择主存储数据库架构方案',
  context: '当前涉及高频读写与多维度全文检索场景',
  questionType: 'single_choice',
  allowSkip: true,
  defaultOptionId: 'opt_sqlite',
  status: 'pending',
  options: [
    {
      id: 'opt_sqlite',
      label: 'SQLite (轻量单机 + WAL 高并发)',
      description: '零依赖、秒级启动、单文件持久化',
      isRecommended: true,
    },
    {
      id: 'opt_postgres',
      label: 'PostgreSQL + pgvector',
      description: '企业级关系存储与向量混排',
    },
    {
      id: 'opt_qdrant',
      label: 'Qdrant (专用高维向量检索引擎)',
      description: '百万级向量亚毫秒过滤检索',
    },
  ],
};

describe('StructuredQuestionCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useStructuredAskingStore.getState().resetAll();
  });

  it('renders pending question card with question, context, options, and recommended badge', async () => {
    await act(async () => {
      render(<StructuredQuestionCard payload={sampleSinglePayload} />);
      await Promise.resolve();
    });

    expect(screen.getByTestId('structured-question-card')).toBeInTheDocument();
    expect(screen.getByText('请选择主存储数据库架构方案')).toBeInTheDocument();
    expect(screen.getByText('当前涉及高频读写与多维度全文检索场景')).toBeInTheDocument();
    expect(screen.getByText('SQLite (轻量单机 + WAL 高并发)')).toBeInTheDocument();
    expect(screen.getByText('recommended')).toBeInTheDocument();
    expect(screen.getByTestId('skip-button')).toBeInTheDocument();
    expect(screen.getByTestId('submit-button')).toBeInTheDocument();
  });

  it('handles option click selection and enables submit button', async () => {
    const onSubmitResponseMock = vi.fn();

    await act(async () => {
      render(
        <StructuredQuestionCard
          payload={sampleSinglePayload}
          onSubmitResponse={onSubmitResponseMock}
        />
      );
      await Promise.resolve();
    });

    const submitBtn = screen.getByTestId('submit-button');
    expect(submitBtn).toBeDisabled();

    // Click option 2 (postgres)
    const opt2Btn = screen.getByTestId('option-item-opt_postgres');
    await act(async () => {
      fireEvent.click(opt2Btn);
      await Promise.resolve();
    });

    expect(submitBtn).not.toBeDisabled();

    // Submit selection
    await act(async () => {
      fireEvent.click(submitBtn);
      await Promise.resolve();
    });

    expect(onSubmitResponseMock).toHaveBeenCalledTimes(1);
    const callArg = onSubmitResponseMock.mock.calls[0][0];
    expect(callArg.selectedOptionIds).toEqual(['opt_postgres']);
    expect(callArg.isSkipped).toBe(false);
  });

  it('supports number keyboard shortcuts (e.g., key 1, 2) and Enter to submit', async () => {
    const onSubmitResponseMock = vi.fn();

    await act(async () => {
      render(
        <StructuredQuestionCard
          payload={sampleSinglePayload}
          onSubmitResponse={onSubmitResponseMock}
          enableKeyboardShortcuts={true}
        />
      );
      await Promise.resolve();
    });

    // Press '1' on keyboard to select option 1
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '1' }));
      await Promise.resolve();
    });

    expect(useStructuredAskingStore.getState().getDraft('q_db_type').selectedOptionIds).toEqual(['opt_sqlite']);

    // Press 'Enter' to submit
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
      await Promise.resolve();
    });

    expect(onSubmitResponseMock).toHaveBeenCalledTimes(1);
    expect(onSubmitResponseMock.mock.calls[0][0].selectedOptionIds).toEqual(['opt_sqlite']);
  });

  it('supports skip control via button click or Escape keyboard shortcut', async () => {
    const onSkipMock = vi.fn();
    const onSubmitResponseMock = vi.fn();

    await act(async () => {
      render(
        <StructuredQuestionCard
          payload={sampleSinglePayload}
          onSkip={onSkipMock}
          onSubmitResponse={onSubmitResponseMock}
          enableKeyboardShortcuts={true}
        />
      );
      await Promise.resolve();
    });

    // Click skip button
    const skipBtn = screen.getByTestId('skip-button');
    await act(async () => {
      fireEvent.click(skipBtn);
      await Promise.resolve();
    });

    expect(onSkipMock).toHaveBeenCalledTimes(1);

    // Escape shortcut triggers skip
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      await Promise.resolve();
    });

    expect(onSkipMock).toHaveBeenCalledTimes(2);
  });

  it('renders answered status view showing selected options summary', async () => {
    const answeredPayload: StructuredQuestionPayload = {
      ...sampleSinglePayload,
      status: 'answered',
      response: {
        selectedOptionIds: ['opt_sqlite'],
        isSkipped: false,
        answeredAt: Date.now(),
      },
    };

    await act(async () => {
      render(<StructuredQuestionCard payload={answeredPayload} />);
      await Promise.resolve();
    });

    expect(screen.getByTestId('status-badge')).toBeInTheDocument();
    expect(screen.getByText('answeredBadge')).toBeInTheDocument();
    expect(screen.getByTestId('answered-summary')).toBeInTheDocument();
    expect(screen.getByText(/SQLite/)).toBeInTheDocument();
    expect(screen.queryByTestId('options-container')).toBeNull();
  });

  it('renders skipped status view showing explanation message', async () => {
    const skippedPayload: StructuredQuestionPayload = {
      ...sampleSinglePayload,
      status: 'skipped',
      response: {
        selectedOptionIds: ['opt_sqlite'],
        isSkipped: true,
        answeredAt: Date.now(),
      },
    };

    await act(async () => {
      render(<StructuredQuestionCard payload={skippedPayload} />);
      await Promise.resolve();
    });

    expect(screen.getByTestId('status-badge')).toBeInTheDocument();
    expect(screen.getByText('skippedBadge')).toBeInTheDocument();
    expect(screen.getByText('skippedExplanation')).toBeInTheDocument();
  });
});
