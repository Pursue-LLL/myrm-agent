/**
 * Unit tests for SecretRedactionPreview component.
 *
 * [INPUT] SecretRedactionPreview, RedactionScan
 * [OUTPUT] Full coverage for the four scan states (scanning, unavailable, clean, found), pattern breakdown, and redaction toggle switch.
 * [POS] src/components/features/session-export/__tests__/SecretRedactionPreview.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SecretRedactionPreview } from '../SecretRedactionPreview';
import type { RedactionSummary } from '../sessionExportTypes';

const stableT = (key: string, values?: Record<string, unknown>) => {
  const translations: Record<string, string> = {
    cleanNoSecrets: 'Clean session: no credentials detected',
    scanningSecrets: 'Scanning this session for credentials...',
    scanUnavailable: "Couldn't scan this session for credentials",
    redactionActiveHint: 'API keys, passwords, and private IPs will be automatically scrubbed upon export.',
    redactionDisabledHint: 'Warning: sensitive keys will be exported in plaintext.',
    autoRedact: 'Auto-Redact',
  };
  if (key === 'secretsDetected' && values) {
    return `${values.count} sensitive credentials detected`;
  }
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('SecretRedactionPreview', () => {
  it('renders clean session message when no secrets detected', () => {
    const onToggle = vi.fn();
    const cleanSummary: RedactionSummary = {
      total_redacted: 0,
      has_secrets: false,
      details: [],
    };

    render(
      <SecretRedactionPreview
        scan={{ status: 'ready', summary: cleanSummary }}
        enableRedaction={true}
        onToggleRedaction={onToggle}
      />,
    );

    expect(screen.getByText('Clean session: no credentials detected')).toBeDefined();
    expect(
      screen.getByText('API keys, passwords, and private IPs will be automatically scrubbed upon export.'),
    ).toBeDefined();
  });

  it('renders warning and details pills when credentials detected', () => {
    const onToggle = vi.fn();
    const dirtySummary: RedactionSummary = {
      total_redacted: 3,
      has_secrets: true,
      details: [
        { pattern_type: 'api_key', count: 2, placeholder: '[REDACTED_API_KEY]' },
        { pattern_type: 'internal_ip', count: 1, placeholder: '[REDACTED_INTERNAL_IP]' },
      ],
    };

    render(
      <SecretRedactionPreview
        scan={{ status: 'ready', summary: dirtySummary }}
        enableRedaction={true}
        onToggleRedaction={onToggle}
      />,
    );

    expect(screen.getByText('3 sensitive credentials detected')).toBeDefined();
    expect(screen.getByText('api_key: 2')).toBeDefined();
    expect(screen.getByText('internal_ip: 1')).toBeDefined();
  });

  it('triggers onToggleRedaction when checkbox is clicked', () => {
    const onToggle = vi.fn();
    const dirtySummary: RedactionSummary = {
      total_redacted: 1,
      has_secrets: true,
      details: [{ pattern_type: 'api_key', count: 1, placeholder: '[REDACTED_API_KEY]' }],
    };

    render(
      <SecretRedactionPreview
        scan={{ status: 'ready', summary: dirtySummary }}
        enableRedaction={true}
        onToggleRedaction={onToggle}
      />,
    );

    const checkbox = screen.getByTestId('redaction-checkbox');
    fireEvent.click(checkbox);
    expect(onToggle).toHaveBeenCalledWith(false);
  });

  it('says the scan is running instead of calling the session clean while it is', () => {
    render(<SecretRedactionPreview scan={{ status: 'scanning' }} enableRedaction={true} onToggleRedaction={vi.fn()} />);

    expect(screen.getByText('Scanning this session for credentials...')).toBeDefined();
    expect(screen.queryByText('Clean session: no credentials detected')).toBeNull();
  });

  it('says the scan could not be done instead of calling the session clean when it failed', () => {
    render(<SecretRedactionPreview scan={{ status: 'failed' }} enableRedaction={true} onToggleRedaction={vi.fn()} />);

    expect(screen.getByText("Couldn't scan this session for credentials")).toBeDefined();
    expect(screen.queryByText('Clean session: no credentials detected')).toBeNull();
  });

  it('keeps the auto-redact switch usable while the scan is running or unavailable', () => {
    const onToggle = vi.fn();
    render(<SecretRedactionPreview scan={{ status: 'failed' }} enableRedaction={true} onToggleRedaction={onToggle} />);

    fireEvent.click(screen.getByTestId('redaction-checkbox'));

    expect(onToggle).toHaveBeenCalledWith(false);
  });
});
