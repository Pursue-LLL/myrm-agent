import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ArchiveRestoreStepAction } from '../ArchiveRestoreStepAction';
import { ArchiveRestoreResultChip } from '../ArchiveRestoreResultChip';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const templates: Record<string, string> = {
      archiveRestoreCardDescription: 'restore actions: {count}',
      archiveRestoreButton: 'restore {count}',
      archiveRestoreContentFeatures: 'features: {features}',
      archiveRestoreMetadataArchive: 'archive: {path}',
      archiveRestoreMetadataFallback: 'fallback: {reason}',
      archiveRestoreMetadataGuidance: 'guidance: {source}',
      archiveRestoreMetadataReason: 'reason: {reason}',
      archiveRestoreMetadataTokens: 'tokens: {tokens}',
      archiveRestoreRangeReason: 'why: {reason}',
      archiveRestoreResultArchive: 'result archive: {path}',
      archiveRestoreResultBytes: 'result bytes: {bytes}',
      archiveRestoreResultRange: 'result range: {range}',
      archiveRestoreResultSummary: 'restored {lines} lines, {tokens} tokens',
      archiveRestoreResultTokens: 'result tokens: {tokens}',
      archiveRestoreSubmitting: 'restoring',
    };
    return Object.entries(values ?? {}).reduce(
      (text, [name, value]) => text.replace(`{${name}}`, String(value)),
      templates[key] ?? key,
    );
  },
}));

describe('ArchiveRestoreStepAction', () => {
  it('renders restore metadata from the archive restore block payload', () => {
    render(
      <ArchiveRestoreStepAction
        actions={[
          {
            type: 'archive_restore',
            restoreArg: '.context/chat-1/compacted/result.txt:20-40',
          },
        ]}
        block={{
          estimated_tokens: 1536,
          reason: 'archive_restore_range_required',
          archive_path: '.context/chat-1/compacted/result.txt',
          guidance_source: 'restore_map',
          fallback_reason: 'size_probe_failed',
          restore_range_hints: [
            {
              range_arg: '.context/chat-1/compacted/result.txt:20-40',
              reason: 'error_keyword',
            },
          ],
          content_features: [
            {
              feature_type: 'error_keyword',
              count: 2,
              values: ['ECONNRESET', 'timeout'],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText('tokens: 1,536')).toBeInTheDocument();
    expect(screen.getByText('reason: Archive Restore Range Required')).toBeInTheDocument();
    expect(screen.getByText('guidance: Restore Map')).toBeInTheDocument();
    expect(screen.getByText('fallback: Size Probe Failed')).toBeInTheDocument();
    expect(screen.getByText('archive: .context/chat-1/compacted/result.txt')).toBeInTheDocument();
    expect(screen.getByText('why: Error Keyword')).toBeInTheDocument();
    expect(screen.getByText('features: Error Keyword (2): ECONNRESET, timeout')).toBeInTheDocument();
  });

  it('renders restore result metadata without restored content', () => {
    render(
      <ArchiveRestoreResultChip
        result={{
          type: 'archive_restore_result',
          outcome: 'restored',
          archive_path: '.context/chat-1/compacted/result.txt',
          restore_arg: '.context/chat-1/compacted/result.txt:20-40',
          start_line: 20,
          end_line: 40,
          restored_line_count: 21,
          estimated_tokens: 640,
          restored_bytes: 2048,
        }}
      />,
    );

    expect(screen.getByText('restored 21 lines, 640 tokens')).toBeInTheDocument();
    expect(screen.getByText('.context/chat-1/compacted/result.txt:20-40')).toBeInTheDocument();
    expect(screen.getByText('result range: 20-40')).toBeInTheDocument();
    expect(screen.getByText('result tokens: 640')).toBeInTheDocument();
    expect(screen.getByText('result bytes: 2,048')).toBeInTheDocument();
    expect(screen.getByText('result archive: .context/chat-1/compacted/result.txt')).toBeInTheDocument();
  });
});
