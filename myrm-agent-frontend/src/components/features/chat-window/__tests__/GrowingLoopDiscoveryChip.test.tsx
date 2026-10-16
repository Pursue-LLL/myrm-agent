/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MemoryStatsResponse } from '@/services/memory/core';
import { GrowingLoopDiscoveryChip } from '../GrowingLoopDiscoveryChip';

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}|${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));

const memoryService = vi.hoisted(() => ({ getMemoryStats: vi.fn() }));

vi.mock('@/services/memory/core', () => memoryService);

const statsWith = (total: number) => ({ total_memories: total, by_type: {} }) as unknown as MemoryStatsResponse;

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

    fireEvent.click(screen.getByRole('button'));
    expect(router.push).toHaveBeenCalledWith('/journey');
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
