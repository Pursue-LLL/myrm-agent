/** @vitest-environment jsdom */

vi.mock('next-intl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-intl')>();
  return {
    ...actual,
    useLocale: () => 'zh',
  };
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { promptCacheZhMessages } from './promptCacheTestMessages';

import { TwoLayerDialecticStudioCard } from '../command-center/TwoLayerDialecticStudioCard';
import {
  FALLBACK_BASE_CONTEXT,
  FALLBACK_CONFLICTS,
  FALLBACK_RECONCILIATION_RESULTS,
} from '../command-center/twoLayerDialecticFallbacks';

const {
  mockAssembleTwoLayerInjection,
  mockGetBaseContextCache,
  mockInspectDialecticConflicts,
  mockReconcileDialecticConflicts,
  mockResetSessionCadence,
} = vi.hoisted(() => ({
  mockAssembleTwoLayerInjection: vi.fn(),
  mockGetBaseContextCache: vi.fn(),
  mockInspectDialecticConflicts: vi.fn(),
  mockReconcileDialecticConflicts: vi.fn(),
  mockResetSessionCadence: vi.fn(),
}));

vi.mock('@/services/memory/twoLayerDialectic', () => ({
  assembleTwoLayerInjection: mockAssembleTwoLayerInjection,
  getBaseContextCache: mockGetBaseContextCache,
  inspectDialecticConflicts: mockInspectDialecticConflicts,
  reconcileDialecticConflicts: mockReconcileDialecticConflicts,
  resetSessionCadence: mockResetSessionCadence,
}));

function renderCard() {
  return render(
    <NextIntlClientProvider locale="zh" messages={promptCacheZhMessages}>
      <TwoLayerDialecticStudioCard />
    </NextIntlClientProvider>,
  );
}

describe('TwoLayerDialecticStudioCard (Item 112 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetBaseContextCache.mockResolvedValue(FALLBACK_BASE_CONTEXT);
    mockAssembleTwoLayerInjection.mockResolvedValue({});
    mockInspectDialecticConflicts.mockResolvedValue(FALLBACK_CONFLICTS);
    mockReconcileDialecticConflicts.mockResolvedValue(FALLBACK_RECONCILIATION_RESULTS);
    mockResetSessionCadence.mockResolvedValue({
      session_id: 'lab_session_preview',
      status: 'reset_success',
      reset_at: '2026-10-08T10:00:00Z',
    });
  });

  it('renders lab banner, title, and layout-stable HUD without fake 100% metrics', async () => {
    renderCard();

    expect(screen.getByText(/仅实验室预览/)).toBeInTheDocument();
    expect(screen.getByText('双层上下文实验室')).toBeInTheDocument();
    expect(screen.getByText('Item 112')).toBeInTheDocument();
    expect(screen.getByText('系统前缀布局')).toBeInTheDocument();
    expect(screen.getByText('稳定')).toBeInTheDocument();
    expect(screen.queryByText(/\b100%\b/)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByText('系统提示词保持稳定，动态记忆挂在用户消息末尾'),
      ).toBeInTheDocument();
    });
  });

  it('switches between base, dialectic, and knobs tabs', async () => {
    renderCard();

    await waitFor(() => {
      expect(screen.getByText('Layer 1 基础布局')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '辩证控制台' }));
    expect(screen.getByText(/典型认知冲突候选库/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '节奏控制' }));
    expect(screen.getByText('节奏与深度控制')).toBeInTheDocument();
  });

  it('calls assemble + getBaseContextCache on force recompile', async () => {
    renderCard();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Recompile snapshot/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Recompile snapshot/i }));

    await waitFor(() => {
      expect(mockAssembleTwoLayerInjection).toHaveBeenCalled();
      expect(mockGetBaseContextCache).toHaveBeenCalled();
      expect(screen.getByText('已从服务器重建基础快照')).toBeInTheDocument();
    });
  });

  it('runs dialectic reconciliation from dialectic tab', async () => {
    renderCard();

    fireEvent.click(screen.getByRole('button', { name: '辩证控制台' }));

    const runBtn = await screen.findByRole('button', {
      name: '执行多遍辩证推理调和',
    });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(mockReconcileDialecticConflicts).toHaveBeenCalledWith({
        statements: expect.any(Array),
        depth: 3,
      });
    });
  });
});
