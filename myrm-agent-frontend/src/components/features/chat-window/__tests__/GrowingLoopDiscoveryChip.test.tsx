/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MemoryStatsResponse, MemoryType } from '@/services/memory/core';
import { GrowingLoopDiscoveryChip } from '../GrowingLoopDiscoveryChip';

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}|${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));

const memoryService = vi.hoisted(() => ({ getMemoryStats: vi.fn() }));

vi.mock('@/services/memory/core', () => memoryService);

const EMPTY_BY_TYPE: Record<MemoryType, number> = {
  profile: 0,
  semantic: 0,
  episodic: 0,
  procedural: 0,
  conversation: 0,
  claim: 0,
  task_digest: 0,
};

const statsWith = (total: number): MemoryStatsResponse => ({ total_memories: total, by_type: EMPTY_BY_TYPE });

describe('GrowingLoopDiscoveryChip', () => {
  beforeEach(() => {
    router.push.mockReset();
    memoryService.getMemoryStats.mockReset();
  });

  it('shows the memory count next to the headline and opens the journey page', async () => {
    memoryService.getMemoryStats.mockResolvedValue(statsWith(40));
    render(<GrowingLoopDiscoveryChip />);

    expect(screen.getByText('growsWithYou')).toBeTruthy();
    expect(await screen.findByText(/memoriesCount\|\{"count":40\}/)).toBeTruthy();
    expect(memoryService.getMemoryStats).toHaveBeenCalledWith({ silent: true });

    fireEvent.click(screen.getByRole('button'));
    expect(router.push).toHaveBeenCalledWith('/journey');
  });

  it('keeps only the headline and the arrow visible below the md breakpoint', async () => {
    memoryService.getMemoryStats.mockResolvedValue(statsWith(40));
    render(<GrowingLoopDiscoveryChip />);

    const count = await screen.findByText(/memoriesCount\|/);
    const tail = screen.getByText(/loopName/);
    const actionLabel = screen.getByText('viewLoop');

    // Long headlines in en/de/ja/ko are cut off on phones unless everything else steps aside.
    for (const secondary of [count, tail]) {
      expect(secondary.classList.contains('hidden')).toBe(true);
      expect(secondary.classList.contains('md:inline')).toBe(true);
    }
    expect(screen.getByText('growsWithYou').classList.contains('hidden')).toBe(false);
    // The action label stays in the button's accessible name even while it is visually hidden.
    expect(actionLabel.classList.contains('sr-only')).toBe(true);
    expect(actionLabel.classList.contains('md:not-sr-only')).toBe(true);
  });

  it('pulses the icon twice and only when the system allows motion', () => {
    memoryService.getMemoryStats.mockReturnValue(new Promise(() => undefined));
    const { container } = render(<GrowingLoopDiscoveryChip />);

    // The sparkles icon is the first svg; the arrow follows it.
    const icon = container.querySelector('svg');
    expect(icon?.classList.contains('motion-safe:animate-[pulse_2s_cubic-bezier(0.4,0,0.6,1)_2]')).toBe(true);
    // The stock utility loops forever, which never lets the page settle for people who are sensitive to motion.
    expect(icon?.classList.contains('animate-pulse')).toBe(false);
  });

  it('renders the entry point right away, before the count request settles', () => {
    memoryService.getMemoryStats.mockReturnValue(new Promise(() => undefined));
    render(<GrowingLoopDiscoveryChip />);

    expect(screen.getByText('growsWithYou')).toBeTruthy();
    expect(screen.getByText('viewLoop')).toBeTruthy();
    expect(screen.queryByText(/memoriesCount\|/)).toBeNull();

    fireEvent.click(screen.getByRole('button'));
    expect(router.push).toHaveBeenCalledWith('/journey');
  });

  it('omits the count when nothing has been remembered yet', async () => {
    memoryService.getMemoryStats.mockResolvedValue(statsWith(0));
    render(<GrowingLoopDiscoveryChip />);

    await waitFor(() => expect(memoryService.getMemoryStats).toHaveBeenCalledTimes(1));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText('growsWithYou')).toBeTruthy();
    expect(screen.queryByText(/memoriesCount\|/)).toBeNull();
  });

  it('keeps the entry point and omits the count when the request fails', async () => {
    memoryService.getMemoryStats.mockRejectedValue(new Error('offline'));
    render(<GrowingLoopDiscoveryChip />);

    await waitFor(() => expect(memoryService.getMemoryStats).toHaveBeenCalledTimes(1));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByText('growsWithYou')).toBeTruthy();
    expect(screen.getByText('viewLoop')).toBeTruthy();
    expect(screen.queryByText(/memoriesCount\|/)).toBeNull();
  });
});
