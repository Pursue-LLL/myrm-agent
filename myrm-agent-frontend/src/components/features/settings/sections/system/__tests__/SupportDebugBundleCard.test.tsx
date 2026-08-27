/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import SupportDebugBundleCard from '../SupportDebugBundleCard';
import { systemService } from '@/services/system';

// Mock next-intl
vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string, params?: Record<string, unknown>) => {
    return `${namespace || 'settings.supportDebugBundle'}.${key}`;
  },
}));

// Mock useToast
const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  toast: (args: unknown) => mockToast(args),
}));

describe('SupportDebugBundleCard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    global.URL.createObjectURL = vi.fn(() => 'blob:mock-url');
    global.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders card title, privacy notice, and switches', () => {
    render(<SupportDebugBundleCard />);

    expect(screen.getByTestId('support-debug-bundle-card')).toBeInTheDocument();
    expect(screen.getByTestId('toggle-include-traces')).toBeInTheDocument();
    expect(screen.getByTestId('toggle-include-profiles')).toBeInTheDocument();
    expect(screen.getByTestId('export-debug-bundle-btn')).toBeInTheDocument();
  });

  it('triggers download and shows success toast when export button clicked', async () => {
    const mockBlob = new Blob(['mock zip content'], { type: 'application/zip' });
    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => mockBlob,
    });

    render(<SupportDebugBundleCard />);

    const exportBtn = screen.getByTestId('export-debug-bundle-btn');
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/system/debug-bundle?include_traces=true&include_profiles=true'),
        { method: 'GET' },
      );
    });

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'settings.supportDebugBundle.exportSuccessTitle',
          description: 'settings.supportDebugBundle.exportSuccessDesc',
        }),
      );
    });
  });

  it('shows error toast when export API returns error response', async () => {
    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
    });

    render(<SupportDebugBundleCard />);

    const exportBtn = screen.getByTestId('export-debug-bundle-btn');
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'settings.supportDebugBundle.exportFailedTitle',
          variant: 'destructive',
        }),
      );
    });
  });
});
