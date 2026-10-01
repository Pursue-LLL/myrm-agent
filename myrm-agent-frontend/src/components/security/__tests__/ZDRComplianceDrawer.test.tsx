import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ZDRComplianceDrawer } from '../ZDRComplianceDrawer';
import type { ZDRSessionState } from '../types';

describe('ZDRComplianceDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockSession: ZDRSessionState = {
    chatId: 'chat_ciso_audit_001',
    isActive: true,
    messageCount: 8,
    totalChars: 12450,
    reconnectGraceSeconds: 60,
  };

  it('renders badge correctly with zero native emoji', () => {
    render(<ZDRComplianceDrawer sessionState={mockSession} />);

    const badge = screen.getByTestId('zdr-status-badge');
    expect(badge).toBeDefined();
    expect(screen.getByText('ZDR Active')).toBeDefined();
    expect(screen.getByText('RAM-Only')).toBeDefined();

    // Verify zero native emoji
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    expect(emojiRegex.test(badge.textContent || '')).toBe(false);
  });

  it('opens drawer dialog and reveals compliance details', () => {
    render(<ZDRComplianceDrawer sessionState={mockSession} />);

    // Click badge to toggle dialog
    fireEvent.click(screen.getByTestId('zdr-status-badge'));

    expect(screen.getByText('Zero Data Retention (ZDR)')).toBeDefined();
    expect(screen.getByText('100% Volatile RAM')).toBeDefined();
    expect(screen.getByText('store=false (ZDR)')).toBeDefined();
    expect(screen.getByText('8 in memory')).toBeDefined();
    expect(screen.getByText('12450 characters')).toBeDefined();
  });

  it('triggers onWipeSession callback on wipe click', async () => {
    const handleWipe = vi.fn().mockResolvedValue(undefined);
    render(
      <ZDRComplianceDrawer
        sessionState={mockSession}
        onWipeSession={handleWipe}
      />
    );

    fireEvent.click(screen.getByTestId('zdr-status-badge'));
    const wipeBtn = screen.getByTestId('zdr-wipe-btn');
    fireEvent.click(wipeBtn);

    await waitFor(() => {
      expect(handleWipe).toHaveBeenCalledWith('chat_ciso_audit_001');
      expect(screen.getByText('Purged (0x00)')).toBeDefined();
    });
  });

  it('triggers onDownloadAttestation callback', async () => {
    const handleDownload = vi.fn().mockResolvedValue(undefined);
    render(
      <ZDRComplianceDrawer
        sessionState={mockSession}
        onDownloadAttestation={handleDownload}
      />
    );

    fireEvent.click(screen.getByTestId('zdr-status-badge'));
    const downloadBtn = screen.getByTestId('zdr-download-btn');
    fireEvent.click(downloadBtn);

    expect(handleDownload).toHaveBeenCalledWith('chat_ciso_audit_001', 'markdown');
  });

  it('does not render when session is inactive and not wiped', () => {
    const inactiveSession: ZDRSessionState = {
      ...mockSession,
      isActive: false,
    };
    const { container } = render(<ZDRComplianceDrawer sessionState={inactiveSession} />);
    expect(container.firstChild).toBeNull();
  });
});
