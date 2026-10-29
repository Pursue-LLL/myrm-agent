/**
 * Unit tests for SessionExportShareModal component.
 *
 * [INPUT] SessionExportShareModal, sessionExportService
 * [OUTPUT] Full coverage for modal lifecycle, tab switching (HTML vs Share Link), compilation download, and link copy.
 * [POS] src/components/features/session-export/__tests__/SessionExportShareModal.test.tsx
 */

import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SessionExportShareModal } from '../SessionExportShareModal';
import { sessionExportService } from '../sessionExportService';
import type { InteractiveHtmlExportResult, RedactionSummary, ShareLinkResponse } from '../sessionExportTypes';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    modalTitle: 'Session Export & Interactive Share Bridge',
    tabDownloadHtml: 'Interactive HTML Bundle',
    tabShareLink: 'Read-Only Web Link',
    includeThinking: 'Include Reasoning & Thinking Traces',
    includeToolCalls: 'Include Tool Call Inputs & Outputs',
    themePreset: 'Default HTML Theme',
    themeSystem: 'System Auto',
    themeLight: 'Light',
    themeDark: 'Dark',
    zeroDepHint: 'Zero External Dependencies',
    linkExpiry: 'Link Expiration Window',
    expiry7Days: '7 Days',
    expiry30Days: '30 Days',
    optionalPassword: 'Optional Passcode Protection',
    passwordPlaceholder: 'Leave empty for public link...',
    shareLinkReady: 'Secure Share Link Ready',
    copied: 'Copied',
    copy: 'Copy',
    cancel: 'Cancel',
    compiling: 'Compiling...',
    compileAndDownload: 'Compile & Download HTML',
    generating: 'Generating...',
    generateLink: 'Generate Share Link',
    cleanNoSecrets: 'Clean session: no credentials detected',
    scanningSecrets: 'Scanning this session for credentials...',
    scanUnavailable: "Couldn't scan this session for credentials",
    exportFailed: "The HTML file couldn't be created. Please try again.",
    shareLinkFailed: "The share link couldn't be created. Please try again.",
    redactionActiveHint: 'Auto-redact active',
    autoRedact: 'Auto-Redact',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SessionExportShareModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(sessionExportService, 'previewRedaction').mockResolvedValue({
      total_redacted: 0,
      has_secrets: false,
      details: [],
    });
  });

  it('renders nothing when isOpen is false', () => {
    render(<SessionExportShareModal chatId="chat-123" isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByTestId('session-export-share-modal')).toBeNull();
  });

  it('renders modal and triggers onClose when close button clicked', async () => {
    const onClose = vi.fn();
    render(
      <SessionExportShareModal chatId="chat-123" chatTitle="Debug Python Sandbox" isOpen={true} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('session-export-share-modal')).toBeDefined();
    });
    expect(screen.getByText('Session Export & Interactive Share Bridge')).toBeDefined();
    expect(screen.getByText('Debug Python Sandbox')).toBeDefined();

    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('switches tabs between HTML export and Share Link', async () => {
    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId('compile-html-btn')).toBeDefined();
    });
    expect(screen.queryByTestId('generate-link-btn')).toBeNull();

    // Click Share Link tab
    const shareTab = screen.getByTestId('tab-share-link');
    fireEvent.click(shareTab);

    expect(screen.getByTestId('generate-link-btn')).toBeDefined();
    expect(screen.queryByTestId('compile-html-btn')).toBeNull();

    // Click back to HTML tab
    const htmlTab = screen.getByTestId('tab-html-export');
    fireEvent.click(htmlTab);
    expect(screen.getByTestId('compile-html-btn')).toBeDefined();
  });

  it('compiles and triggers download of standalone HTML', async () => {
    const mockExportResult: InteractiveHtmlExportResult = {
      chat_id: 'chat-123',
      title: 'Debug Python Sandbox',
      file_name: 'myrm-session-test.html',
      html_content: '<!DOCTYPE html><html><body>Test</body></html>',
      size_bytes: 42,
      total_messages: 2,
      redaction_summary: {
        total_redacted: 0,
        has_secrets: false,
        details: [],
      },
    };

    const onClose = vi.fn();
    vi.spyOn(sessionExportService, 'exportInteractiveHtml').mockResolvedValueOnce(mockExportResult);
    const triggerDownloadSpy = vi.spyOn(sessionExportService, 'triggerDownload').mockImplementation(() => {});

    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={onClose} />);

    const compileBtn = screen.getByTestId('compile-html-btn');
    fireEvent.click(compileBtn);

    await waitFor(() => {
      expect(sessionExportService.exportInteractiveHtml).toHaveBeenCalledWith('chat-123', {
        include_thinking: true,
        include_tool_calls: true,
        enable_redaction: true,
        theme: 'system',
      });
      expect(triggerDownloadSpy).toHaveBeenCalledWith(
        'myrm-session-test.html',
        '<!DOCTYPE html><html><body>Test</body></html>',
      );
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  it('generates HMAC share link and allows copying to clipboard', async () => {
    const mockShareResponse: ShareLinkResponse = {
      chat_id: 'chat-123',
      share_url: 'http://localhost:3000/share/test-hmac-token',
      share_token: 'test-hmac-token',
      expires_at_unix: 1800000000,
      is_password_protected: false,
    };

    vi.spyOn(sessionExportService, 'createShareLink').mockResolvedValueOnce(mockShareResponse);
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={vi.fn()} />);

    // Switch to share link tab
    fireEvent.click(screen.getByTestId('tab-share-link'));

    const generateBtn = screen.getByTestId('generate-link-btn');
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(screen.getByTestId('share-url-input')).toBeDefined();
    });

    const input = screen.getByTestId('share-url-input') as HTMLInputElement;
    expect(input.value).toBe('http://localhost:3000/share/test-hmac-token');

    // Click Copy button
    const copyBtn = screen.getByTestId('copy-link-btn');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('http://localhost:3000/share/test-hmac-token');
      expect(screen.getByText('Copied')).toBeDefined();
    });
  });

  it('scans the stored conversation of the chat, not its title', async () => {
    render(<SessionExportShareModal chatId="chat-123" chatTitle="Debug Python Sandbox" isOpen={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(sessionExportService.previewRedaction).toHaveBeenCalledWith('chat-123');
    });
    expect(sessionExportService.previewRedaction).toHaveBeenCalledTimes(1);
    expect(await screen.findByText('Clean session: no credentials detected')).toBeDefined();
  });

  it('does not call the session clean when the scan fails', async () => {
    vi.spyOn(sessionExportService, 'previewRedaction').mockRejectedValue(new Error('offline'));

    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={vi.fn()} />);

    expect(await screen.findByText("Couldn't scan this session for credentials")).toBeDefined();
    expect(screen.queryByText('Clean session: no credentials detected')).toBeNull();
  });

  it('keeps the dialog open, downloads nothing and says so when the export fails', async () => {
    vi.spyOn(sessionExportService, 'exportInteractiveHtml').mockRejectedValueOnce(new Error('offline'));
    const triggerDownloadSpy = vi.spyOn(sessionExportService, 'triggerDownload').mockImplementation(() => {});
    const onClose = vi.fn();

    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByTestId('compile-html-btn'));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe("The HTML file couldn't be created. Please try again.");
    expect(triggerDownloadSpy).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect((screen.getByTestId('compile-html-btn') as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows no link and says so when the share link cannot be created', async () => {
    vi.spyOn(sessionExportService, 'createShareLink').mockRejectedValueOnce(new Error('unauthorized'));

    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('tab-share-link'));
    fireEvent.click(screen.getByTestId('generate-link-btn'));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe("The share link couldn't be created. Please try again.");
    expect(screen.queryByTestId('share-url-input')).toBeNull();
  });

  it('drops a failure notice when the user moves to the other tab', async () => {
    vi.spyOn(sessionExportService, 'exportInteractiveHtml').mockRejectedValueOnce(new Error('offline'));

    render(<SessionExportShareModal chatId="chat-123" isOpen={true} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('compile-html-btn'));
    await screen.findByRole('alert');

    fireEvent.click(screen.getByTestId('tab-share-link'));

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('ignores a scan that finishes after the user opened another chat', async () => {
    let resolveFirst: (summary: RedactionSummary) => void = () => {};
    const previewSpy = vi.spyOn(sessionExportService, 'previewRedaction');
    previewSpy.mockReturnValueOnce(new Promise<RedactionSummary>((resolve) => { resolveFirst = resolve; }));
    previewSpy.mockResolvedValueOnce({ total_redacted: 0, has_secrets: false, details: [] });

    const { rerender } = render(<SessionExportShareModal chatId="chat-a" isOpen={true} onClose={vi.fn()} />);
    rerender(<SessionExportShareModal chatId="chat-b" isOpen={true} onClose={vi.fn()} />);
    await screen.findByText('Clean session: no credentials detected');

    await act(async () => {
      resolveFirst({
        total_redacted: 1,
        has_secrets: true,
        details: [{ pattern_type: 'api_key', count: 1, placeholder: '[REDACTED_API_KEY]' }],
      });
    });

    expect(screen.queryByText('api_key: 1')).toBeNull();
    expect(screen.getByText('Clean session: no credentials detected')).toBeDefined();
  });
});
