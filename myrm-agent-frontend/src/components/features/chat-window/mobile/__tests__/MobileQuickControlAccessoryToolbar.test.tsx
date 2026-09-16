/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobileQuickControlAccessoryToolbar } from '../MobileQuickControlAccessoryToolbar';

const { mockToast } = vi.hoisted(() => ({
  mockToast: {
    error: vi.fn(),
    info: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock('sonner', () => ({
  toast: mockToast,
}));

const translationMap: Record<string, string> = {
  history: '历史',
  historyNav: '历史指令',
  paste: '粘贴',
  advisorAsk: '问顾问',
  clear: '清空',
  pasteError: '读取剪贴板失败，请检查授权',
  clipboardEmpty: '剪贴板内容为空',
};
const stableT = (key: string) => translationMap[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('MobileQuickControlAccessoryToolbar', () => {
  const onNavigateHistory = vi.fn();
  const onPasteText = vi.fn();
  const onOpenAdvisor = vi.fn();
  const onClearInput = vi.fn();
  const onRequestFocusInput = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders accessory buttons correctly', () => {
    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={3}
        historyCurrentIndex={-1}
        currentValue=""
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    expect(screen.getByText('历史')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();
    expect(screen.getByText('粘贴')).toBeDefined();
    expect(screen.getByText('问顾问')).toBeDefined();
    expect(screen.queryByText('清空')).toBeNull();
  });

  it('disables history button when historyCount is 0', () => {
    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={0}
        historyCurrentIndex={-1}
        currentValue=""
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    const historyBtn = screen.getByRole('button', { name: /历史/i });
    expect(historyBtn.hasAttribute('disabled')).toBe(true);
  });

  it('displays active history index badge when browsing history', () => {
    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={5}
        historyCurrentIndex={2}
        currentValue="some history prompt"
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    expect(screen.getByText('3/5')).toBeDefined();
  });

  it('triggers onNavigateHistory and onOpenAdvisor clicks', () => {
    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={2}
        historyCurrentIndex={-1}
        currentValue=""
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /历史/i }));
    expect(onNavigateHistory).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /问顾问/i }));
    expect(onOpenAdvisor).toHaveBeenCalledTimes(1);
  });

  it('renders clear button when currentValue is present and triggers onClearInput', () => {
    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={2}
        historyCurrentIndex={-1}
        currentValue="typed text"
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    const clearBtn = screen.getByRole('button', { name: /清空/i });
    expect(clearBtn).toBeDefined();
    fireEvent.click(clearBtn);
    expect(onClearInput).toHaveBeenCalledTimes(1);
  });

  it('reads clipboard and calls onPasteText', async () => {
    const mockClipboard = {
      readText: vi.fn().mockResolvedValue('Pasted text from clipboard'),
    };
    Object.assign(navigator, { clipboard: mockClipboard });

    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={0}
        historyCurrentIndex={-1}
        currentValue=""
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    const pasteBtn = screen.getByRole('button', { name: /粘贴/i });
    await act(async () => {
      fireEvent.click(pasteBtn);
    });

    expect(onPasteText).toHaveBeenCalledWith('Pasted text from clipboard');
  });

  it('triggers onRequestFocusInput and prevents default on mousedown', async () => {
    const mockClipboard = {
      readText: vi.fn().mockResolvedValue('text to paste'),
    };
    Object.assign(navigator, { clipboard: mockClipboard });

    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={2}
        historyCurrentIndex={-1}
        currentValue="some draft"
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
        onRequestFocusInput={onRequestFocusInput}
      />,
    );

    const historyBtn = screen.getByRole('button', { name: /历史/i });
    const mousedownEvent = new MouseEvent('mousedown', { cancelable: true, bubbles: true });
    historyBtn.dispatchEvent(mousedownEvent);
    expect(mousedownEvent.defaultPrevented).toBe(true);

    fireEvent.click(historyBtn);
    expect(onNavigateHistory).toHaveBeenCalledTimes(1);
    expect(onRequestFocusInput).toHaveBeenCalledTimes(1);

    const pasteBtn = screen.getByRole('button', { name: /粘贴/i });
    await act(async () => {
      fireEvent.click(pasteBtn);
    });
    expect(onRequestFocusInput).toHaveBeenCalledTimes(2);

    const clearBtn = screen.getByRole('button', { name: /清空/i });
    fireEvent.click(clearBtn);
    expect(onClearInput).toHaveBeenCalledTimes(1);
    expect(onRequestFocusInput).toHaveBeenCalledTimes(3);
  });

  it('shows toast.info when clipboard is empty', async () => {
    const mockClipboard = {
      readText: vi.fn().mockResolvedValue('   '),
    };
    Object.assign(navigator, { clipboard: mockClipboard });

    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={0}
        historyCurrentIndex={-1}
        currentValue=""
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    const pasteBtn = screen.getByRole('button', { name: /粘贴/i });
    await act(async () => {
      fireEvent.click(pasteBtn);
    });

    expect(onPasteText).not.toHaveBeenCalled();
    expect(mockToast.info).toHaveBeenCalledWith('剪贴板内容为空');
  });

  it('shows toast.error when clipboard throws error', async () => {
    const mockClipboard = {
      readText: vi.fn().mockRejectedValue(new Error('Permission denied')),
    };
    Object.assign(navigator, { clipboard: mockClipboard });

    render(
      <MobileQuickControlAccessoryToolbar
        chatId="chat-1"
        historyCount={0}
        historyCurrentIndex={-1}
        currentValue=""
        onNavigateHistory={onNavigateHistory}
        onPasteText={onPasteText}
        onOpenAdvisor={onOpenAdvisor}
        onClearInput={onClearInput}
      />,
    );

    const pasteBtn = screen.getByRole('button', { name: /粘贴/i });
    await act(async () => {
      fireEvent.click(pasteBtn);
    });

    expect(onPasteText).not.toHaveBeenCalled();
    expect(mockToast.error).toHaveBeenCalledWith('读取剪贴板失败，请检查授权');
  });
});
