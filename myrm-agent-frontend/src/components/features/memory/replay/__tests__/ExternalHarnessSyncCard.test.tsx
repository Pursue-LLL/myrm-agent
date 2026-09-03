/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  toast: (...args: any[]) => mockToast(...args),
}));

const stableT = (key: string, params?: Record<string, unknown>) => {
  const translations: Record<string, string> = {
    title: 'External Agent Recall',
    description: 'Seamlessly recall past sessions from Claude Code or Codex.',
    activeBadge: 'Real-time Sync Active',
    pickDirectoryBtn: 'Pick Local Folder',
    syncNowBtn: 'Sync Now',
    trackedFiles: 'Tracked Transcripts',
    defaultPath: 'Auto-scan Path',
    lastSynced: 'Last Synced',
    neverSynced: 'Never',
    syncSuccess: 'Transcripts Synchronized',
    syncSuccessDesc: 'Successfully synced files.',
    browserNotSupported: 'Directory Picker Unavailable',
    browserNotSupportedDesc: 'Your browser environment does not support directory selection.',
  };
  return translations[key] || key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const mockGetStatus = vi.fn();
const mockSync = vi.fn();

vi.mock('@/services/memory/externalTranscripts', () => ({
  getExternalTranscriptStatus: () => mockGetStatus(),
  syncExternalTranscripts: (req: any) => mockSync(req),
}));

import ExternalHarnessSyncCard from '../ExternalHarnessSyncCard';

describe('ExternalHarnessSyncCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial transcript status with tracked count and default path', async () => {
    mockGetStatus.mockResolvedValueOnce({
      enabled: true,
      tracked_files_count: 5,
      last_synced_at: '2026-09-03T10:00:00Z',
      default_directory: '~/.claude/projects',
    });

    render(<ExternalHarnessSyncCard />);

    expect(screen.getByText('External Agent Recall')).toBeInTheDocument();
    expect(screen.getByText('Real-time Sync Active')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalledTimes(1);
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('~/.claude/projects')).toBeInTheDocument();
    });
  });

  it('triggers incremental sync when clicking Sync Now button', async () => {
    mockGetStatus.mockResolvedValue({
      enabled: true,
      tracked_files_count: 5,
      last_synced_at: null,
      default_directory: '~/.claude/projects',
    });

    mockSync.mockResolvedValueOnce({
      synced_files: 2,
      new_turns: 4,
      affected_chats: ['chat-1'],
      skipped_files: 0,
      errors: [],
    });

    render(<ExternalHarnessSyncCard />);

    const syncButton = screen.getByText('Sync Now');
    fireEvent.click(syncButton);

    await waitFor(() => {
      expect(mockSync).toHaveBeenCalledWith({});
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Transcripts Synchronized',
        })
      );
    });
  });

  it('notifies user when browser does not support directory picker', () => {
    mockGetStatus.mockResolvedValue({
      enabled: true,
      tracked_files_count: 0,
      last_synced_at: null,
      default_directory: '~/.claude/projects',
    });

    render(<ExternalHarnessSyncCard />);

    const pickButton = screen.getByText('Pick Local Folder');
    fireEvent.click(pickButton);

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Directory Picker Unavailable',
        variant: 'destructive',
      })
    );
  });
});
