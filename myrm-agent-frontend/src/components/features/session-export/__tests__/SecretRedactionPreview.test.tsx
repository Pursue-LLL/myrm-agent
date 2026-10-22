/**
 * Unit tests for SecretRedactionPreview component.
 *
 * [INPUT] SecretRedactionPreview, RedactionSummary
 * [OUTPUT] Full coverage for detection badge, pattern breakdown, and redaction toggle switch.
 * [POS] src/components/features/session-export/__tests__/SecretRedactionPreview.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SecretRedactionPreview } from '../SecretRedactionPreview';
import type { RedactionSummary } from '../sessionExportTypes';

const stableT = (key: string, values?: Record<string, unknown>) => {
  const translations: Record<string, string> = {
    cleanNoSecrets: 'Clean session: no credentials detected',
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
      <SecretRedactionPreview redactionSummary={cleanSummary} enableRedaction={true} onToggleRedaction={onToggle} />,
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
      <SecretRedactionPreview redactionSummary={dirtySummary} enableRedaction={true} onToggleRedaction={onToggle} />,
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
      <SecretRedactionPreview redactionSummary={dirtySummary} enableRedaction={true} onToggleRedaction={onToggle} />,
    );

    const checkbox = screen.getByTestId('redaction-checkbox');
    fireEvent.click(checkbox);
    expect(onToggle).toHaveBeenCalledWith(false);
  });
});
