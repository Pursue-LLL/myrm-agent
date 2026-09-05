'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import MemoryHygieneDiscoverChip from '../MemoryHygieneDiscoverChip';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const translations: Record<string, string> = {
  title: '5 分钟记忆体检',
  subtitle: '主动审查陈旧记忆与容量水位，一键自愈与规范化',
  action: '立即体检',
  dismiss: '稍后再看',
  hermesBadge: 'Hermes 迁民健康标准',
};
const stableT = (key: string) => translations[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('MemoryHygieneDiscoverChip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('renders correctly when not dismissed', () => {
    render(<MemoryHygieneDiscoverChip />);
    expect(screen.getByTestId('memory-hygiene-discover-chip')).toBeInTheDocument();
    expect(screen.getByText('5 分钟记忆体检')).toBeInTheDocument();
    expect(screen.getByText('Hermes 迁民健康标准')).toBeInTheDocument();
  });

  it('navigates to memory settings doctor panel on click', () => {
    render(<MemoryHygieneDiscoverChip />);
    const chip = screen.getByTestId('memory-hygiene-discover-chip');
    fireEvent.click(chip);
    expect(mockPush).toHaveBeenCalledWith('/settings/memory?sub=command-center&focus=doctor');
  });

  it('dismisses when close button is clicked', () => {
    render(<MemoryHygieneDiscoverChip />);
    const dismissBtn = screen.getByRole('button', { name: '稍后再看' });
    fireEvent.click(dismissBtn);

    expect(screen.queryByTestId('memory-hygiene-discover-chip')).not.toBeInTheDocument();
    expect(sessionStorage.getItem('myrm_memory_hygiene_chip_dismissed')).toBe('true');
  });

  it('does not render if previously dismissed in sessionStorage', () => {
    sessionStorage.setItem('myrm_memory_hygiene_chip_dismissed', 'true');
    render(<MemoryHygieneDiscoverChip />);
    expect(screen.queryByTestId('memory-hygiene-discover-chip')).not.toBeInTheDocument();
  });
});
