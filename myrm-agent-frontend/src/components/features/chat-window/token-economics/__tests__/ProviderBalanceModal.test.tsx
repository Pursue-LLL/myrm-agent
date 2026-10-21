import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ProviderBalanceModal } from '../ProviderBalanceModal';
import { useTokenEconomicsStore } from '../useTokenEconomicsStore';

describe('ProviderBalanceModal', () => {
  beforeEach(() => {
    act(() => {
      useTokenEconomicsStore.getState().resetStore();
    });
  });

  it('renders nothing when modal is closed', () => {
    const { container } = render(<ProviderBalanceModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders provider balance cards when open', () => {
    act(() => {
      useTokenEconomicsStore.getState().toggleBalanceModal(true);
    });

    render(<ProviderBalanceModal />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Provider 账户余额即时自省')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek')).toBeInTheDocument();
    expect(screen.getByText('OpenAI')).toBeInTheDocument();
    expect(screen.getByText('Anthropic')).toBeInTheDocument();
    expect(screen.getByText('阿里百炼')).toBeInTheDocument();

    expect(screen.getByTestId('balance-card-deepseek')).toBeInTheDocument();
    expect(screen.getByTestId('balance-card-openai')).toBeInTheDocument();
  });

  it('triggers refreshProviderBalances on refresh button click', async () => {
    act(() => {
      useTokenEconomicsStore.getState().toggleBalanceModal(true);
    });

    render(<ProviderBalanceModal />);

    const refreshBtn = screen.getByLabelText('重新探测刷新余额');
    act(() => {
      fireEvent.click(refreshBtn);
    });

    expect(useTokenEconomicsStore.getState().isLoadingBalances).toBe(true);

    await act(async () => {
      await vi.waitFor(() => {
        expect(useTokenEconomicsStore.getState().isLoadingBalances).toBe(false);
      });
    });
  });

  it('closes modal on close icon button and footer button click', () => {
    act(() => {
      useTokenEconomicsStore.getState().toggleBalanceModal(true);
    });

    const onClose = vi.fn();
    const { rerender } = render(<ProviderBalanceModal onClose={onClose} />);

    // Click top close button
    const closeBtn = screen.getByLabelText('关闭对话框');
    fireEvent.click(closeBtn);

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(false);

    // Reopen and click footer button
    act(() => {
      useTokenEconomicsStore.getState().toggleBalanceModal(true);
    });
    rerender(<ProviderBalanceModal onClose={onClose} />);

    const finishBtn = screen.getByText('完成查看');
    fireEvent.click(finishBtn);

    expect(onClose).toHaveBeenCalledTimes(2);
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(false);
  });

  it('closes modal on Escape key press and backdrop click', () => {
    act(() => {
      useTokenEconomicsStore.getState().toggleBalanceModal(true);
    });

    render(<ProviderBalanceModal />);

    // Press Escape
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(false);

    // Reopen and click backdrop
    act(() => {
      useTokenEconomicsStore.getState().toggleBalanceModal(true);
    });

    const backdrop = screen.getByTestId('provider-balance-backdrop');
    fireEvent.click(backdrop);
    expect(useTokenEconomicsStore.getState().isBalanceModalOpen).toBe(false);
  });
});
