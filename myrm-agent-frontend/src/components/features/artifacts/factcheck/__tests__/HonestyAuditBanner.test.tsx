/** @vitest-environment jsdom */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HonestyAuditBanner } from '../HonestyAuditBanner';

const stableT = (key: string, values?: Record<string, string | number>) => {
  const table: Record<string, string> = {
    bannerTitle: '诚实守卫与待核验提示',
    bannerSuccess: '所有占位数据已全部核验并替换为真实数据',
    viewCheckSheet: '查看核验清单',
    finalizeDraft: '一键定稿',
  };
  if (key === 'bannerWarning' && values?.count !== undefined) {
    return `本篇草案包含 ${values.count} 处待实测占位数据`;
  }
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('HonestyAuditBanner', () => {
  it('does not render when totalCount is 0', () => {
    const { container } = render(<HonestyAuditBanner pendingCount={0} totalCount={0} onOpenDrawer={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders warning banner with pending count when pendingCount > 0', () => {
    const handleOpen = vi.fn();

    render(<HonestyAuditBanner pendingCount={4} totalCount={5} onOpenDrawer={handleOpen} />);

    expect(screen.getByRole('region')).toBeInTheDocument();
    expect(screen.getByText(/诚实守卫与待核验提示/i)).toBeInTheDocument();
    expect(screen.getByText(/包含 4 处待实测占位数据/i)).toBeInTheDocument();

    const checkSheetBtn = screen.getByRole('button', { name: /查看核验清单/i });
    expect(checkSheetBtn).toBeInTheDocument();

    fireEvent.click(checkSheetBtn);
    expect(handleOpen).toHaveBeenCalledTimes(1);
  });

  it('renders success state and finalize button when pendingCount is 0', () => {
    const handleFinalize = vi.fn();

    render(<HonestyAuditBanner pendingCount={0} totalCount={3} onOpenDrawer={vi.fn()} onFinalize={handleFinalize} />);

    expect(screen.getByText('所有占位数据已全部核验并替换为真实数据')).toBeInTheDocument();

    const finalizeBtn = screen.getByRole('button', { name: /一键定稿/i });
    expect(finalizeBtn).toBeInTheDocument();

    fireEvent.click(finalizeBtn);
    expect(handleFinalize).toHaveBeenCalledTimes(1);
  });
});
