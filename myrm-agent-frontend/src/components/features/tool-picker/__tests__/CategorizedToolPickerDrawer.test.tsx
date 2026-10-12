/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CategorizedToolPickerDrawer } from '../CategorizedToolPickerDrawer';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconSearch: () => <span data-testid="icon-search" />,
  IconX: () => <span data-testid="icon-x" />,
  IconWrench: () => <span data-testid="icon-wrench" />,
  IconCheck: () => <span data-testid="icon-check" />,
}));

describe('CategorizedToolPickerDrawer component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModalMock(
        this: HTMLDialogElement,
      ) {
        this.open = true;
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function closeMock(
        this: HTMLDialogElement,
      ) {
        this.open = false;
      };
    }
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <CategorizedToolPickerDrawer isOpen={false} onClose={vi.fn()} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders drawer header, tabs, and default preset tools when open', () => {
    render(
      <CategorizedToolPickerDrawer isOpen={true} onClose={vi.fn()} />,
    );

    expect(screen.getByText('modalTitle')).toBeDefined();
    expect(screen.getByText('modalSubtitle')).toBeDefined();
    expect(screen.getByPlaceholderText('searchPlaceholder')).toBeDefined();
    expect(screen.getAllByText('电脑与系统控制').length).toBeGreaterThan(0);
    expect(screen.getAllByText('无头浏览器与网页提取').length).toBeGreaterThan(0);
  });

  it('switches category when clicking category tab', () => {
    render(
      <CategorizedToolPickerDrawer isOpen={true} onClose={vi.fn()} />,
    );

    // Switch to system category
    const systemTab = screen.getByText('tabSystem');
    fireEvent.click(systemTab);

    expect(screen.getByText('电脑与系统控制')).toBeDefined();
    expect(screen.getByText('终端命令执行')).toBeDefined();
    // Browser tools should not appear in system tab
    expect(screen.queryByText('无头浏览器与网页提取')).toBeNull();
  });

  it('filters tools by instant search input and clears search', () => {
    render(
      <CategorizedToolPickerDrawer isOpen={true} onClose={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('searchPlaceholder');
    fireEvent.change(input, { target: { value: 'bash' } });

    expect(screen.getByText('终端命令执行')).toBeDefined();
    expect(screen.queryByText('电脑与系统控制')).toBeNull();

    // Click clear search button
    const clearBtn = screen.getByLabelText('clearSearch');
    fireEvent.click(clearBtn);

    expect(screen.getAllByText('电脑与系统控制').length).toBeGreaterThan(0);
  });

  it('filters tools by pinyin acronym', () => {
    render(
      <CategorizedToolPickerDrawer isOpen={true} onClose={vi.fn()} />,
    );

    const input = screen.getByPlaceholderText('searchPlaceholder');
    fireEvent.change(input, { target: { value: 'dnkz' } });

    expect(screen.getByText('电脑与系统控制')).toBeDefined();
    expect(screen.queryByText('终端命令执行')).toBeNull();
  });

  it('calls onSelectTool and closes drawer on close click', () => {
    const handleSelect = vi.fn();
    const handleClose = vi.fn();

    render(
      <CategorizedToolPickerDrawer
        isOpen={true}
        onClose={handleClose}
        onSelectTool={handleSelect}
      />,
    );

    // Click a tool card
    const toolTitle = screen.getAllByText('电脑与系统控制')[0];
    fireEvent.click(toolTitle);

    expect(handleSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'computer_control' }),
    );

    // Click close button
    const closeBtn = screen.getByLabelText('closeAriaLabel');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalled();
  });
});
