import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { SanitizedDebugShareModal } from '../SanitizedDebugShareModal';
import type { EphemeralShareLink, SanitizedDebugDump } from '../sanitizedDebugTypes';

describe('SanitizedDebugShareModal', () => {
  const mockDump: SanitizedDebugDump = {
    dump_id: 'dump_test12345678',
    vitals: {
      os_name: 'Darwin 24.0.0 (arm64)',
      python_version: '3.13.1',
      cpu_cores: 8,
      memory_total_gb: 16.0,
      network_connectivity: 'CONNECTED',
      timestamp: '2026-10-12T12:00:00Z',
    },
    sanitized_logs: [
      '2026-10-12 INFO Authenticating with [REDACTED_API_KEY]',
      'Authorization: Bearer [REDACTED_TOKEN]',
    ],
    recent_traces: [
      {
        event: 'tool_call',
        path: '[USER_WORKSPACE]/path/config.json',
      },
    ],
    redacted_audits: [
      {
        rule_type: 'API_KEY',
        masked_placeholder: '[REDACTED_API_KEY]',
        occurrences_count: 1,
      },
      {
        rule_type: 'BEARER_TOKEN',
        masked_placeholder: 'Bearer [REDACTED_TOKEN]',
        occurrences_count: 1,
      },
    ],
    total_redacted_count: 2,
    user_note: 'Clean user note for triage',
    checksum_sha256: 'a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef',
    created_at: '2026-10-12T12:00:00Z',
  };

  const mockShareLink: EphemeralShareLink = {
    share_token: 'share_sec123token',
    dump_id: 'dump_test12345678',
    share_url: 'https://debug.myrm.ai/share/share_sec123token',
    expires_at: '2026-10-14T12:00:00Z',
    max_views: 3,
    remaining_views: 3,
    is_destroyed: false,
    created_at: '2026-10-12T12:00:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    const handleClose = vi.fn();
    render(<SanitizedDebugShareModal isOpen={false} onClose={handleClose} />);
    expect(screen.queryByTestId('sanitized-debug-share-modal')).not.toBeInTheDocument();
  });

  it('renders initial form and generates sanitized debug dump', async () => {
    const handleClose = vi.fn();
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockDump),
        } as unknown as Response)
    );

    render(
      <SanitizedDebugShareModal
        isOpen={true}
        onClose={handleClose}
        rawLogs={['raw secret log']}
      />
    );

    expect(screen.getByText('零外泄调试包导出与阅后即焚分享')).toBeInTheDocument();
    expect(screen.getByTestId('generate-dump-btn')).toBeInTheDocument();

    // 输入留言并点击生成
    const noteInput = screen.getByTestId('user-note-input');
    fireEvent.change(noteInput, { target: { value: 'Crash on LLM token limit' } });
    fireEvent.click(screen.getByTestId('generate-dump-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('dump-preview-section')).toBeInTheDocument();
    });

    expect(screen.getByTestId('redacted-count')).toHaveTextContent('2 项');
    expect(screen.getByText(/Darwin \/ Python 3.13.1/)).toBeInTheDocument();
  });

  it('supports tabs switching and renders logs and audits', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockDump),
        } as unknown as Response)
    );

    render(<SanitizedDebugShareModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('generate-dump-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('dump-preview-section')).toBeInTheDocument();
    });

    // 切换到脱敏日志 Tab
    fireEvent.click(screen.getByTestId('tab-logs'));
    expect(screen.getByTestId('sanitized-logs-view')).toBeInTheDocument();
    expect(screen.getByText(/Authenticating with \[REDACTED_API_KEY\]/)).toBeInTheDocument();

    // 切换到脱敏抹除审计 Tab
    fireEvent.click(screen.getByTestId('tab-audits'));
    expect(screen.getByTestId('redacted-audits-view')).toBeInTheDocument();
    expect(screen.getByText('API_KEY')).toBeInTheDocument();
    expect(screen.getAllByText('×1')).toHaveLength(2);
  });

  it('generates ephemeral share link and copies URL', async () => {
    const handleShareCreated = vi.fn();
    vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(
        () =>
          Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockDump),
          } as unknown as Response)
      )
      .mockImplementationOnce(
        () =>
          Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockShareLink),
          } as unknown as Response)
      );

    // Mock clipboard
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });

    render(
      <SanitizedDebugShareModal
        isOpen={true}
        onClose={vi.fn()}
        onShareCreated={handleShareCreated}
      />
    );
    fireEvent.click(screen.getByTestId('generate-dump-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('create-ephemeral-link-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('create-ephemeral-link-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('share-link-card')).toBeInTheDocument();
    });

    expect(handleShareCreated).toHaveBeenCalledWith(mockShareLink);
    expect(screen.getByTestId('share-url-input')).toHaveValue(mockShareLink.share_url);

    // 测试复制按钮
    fireEvent.click(screen.getByTestId('copy-link-btn'));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(mockShareLink.share_url);
    expect(screen.getByText('已复制')).toBeInTheDocument();
  });

  it('downloads .myrmdiag file on export button click', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockDump),
        } as unknown as Response)
    );

    const createObjectURLMock = vi.fn(() => 'blob:mock-url');
    const revokeObjectURLMock = vi.fn();
    globalThis.URL.createObjectURL = createObjectURLMock;
    globalThis.URL.revokeObjectURL = revokeObjectURLMock;

    render(<SanitizedDebugShareModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('generate-dump-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('download-diag-file-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('download-diag-file-btn'));
    expect(createObjectURLMock).toHaveBeenCalled();
  });

  it('handles error state properly', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        Promise.resolve({
          ok: false,
          status: 500,
        } as unknown as Response)
    );

    render(<SanitizedDebugShareModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('generate-dump-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('error-alert')).toBeInTheDocument();
    });
    expect(screen.getByTestId('error-alert')).toHaveTextContent('生成脱敏诊断包失败 (HTTP 500)');
  });
});
