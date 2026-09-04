import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PluginTrustedSourceDisclosure } from '../PluginTrustedSourceDisclosure';

const mockIsSandbox = vi.fn();
vi.mock('@/lib/deploy-mode', () => ({
  isSandbox: () => mockIsSandbox(),
}));

const stableT = (key: string) => {
  const map: Record<string, string> = {
    trustDisclosureTitle: 'Trusted Source & System Permissions Security Disclosure',
    trustDisclosureLocal: 'Running in Local/Desktop mode. Full host OS permissions.',
    trustDisclosureCloud: 'Running in Cloud Sandbox mode. Dedicated isolated volume.',
    trustRiskHint: 'Untrusted extensions may contain prompt injection.',
    trustedCheckboxLabel: 'I confirm this plugin is from a trusted source',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PluginTrustedSourceDisclosure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsSandbox.mockReturnValue(false);
  });

  it('renders title, risk hint, and local OS permissions badge when not in sandbox', () => {
    mockIsSandbox.mockReturnValue(false);
    render(<PluginTrustedSourceDisclosure trusted={false} onTrustChange={vi.fn()} />);

    expect(screen.getByText('Trusted Source & System Permissions Security Disclosure')).toBeInTheDocument();
    expect(screen.getByText('Running in Local/Desktop mode. Full host OS permissions.')).toBeInTheDocument();
    expect(screen.getByText('Local OS Permissions')).toBeInTheDocument();
    expect(screen.getByText('Untrusted extensions may contain prompt injection.')).toBeInTheDocument();
  });

  it('renders cloud sandbox badge and cloud notice when in sandbox mode', () => {
    mockIsSandbox.mockReturnValue(true);
    render(<PluginTrustedSourceDisclosure trusted={false} onTrustChange={vi.fn()} />);

    expect(screen.getByText('Cloud Sandbox')).toBeInTheDocument();
    expect(screen.getByText('Running in Cloud Sandbox mode. Dedicated isolated volume.')).toBeInTheDocument();
  });

  it('toggles checkbox and fires onTrustChange callback with new boolean state', () => {
    const onTrustChange = vi.fn();
    const { rerender } = render(<PluginTrustedSourceDisclosure trusted={false} onTrustChange={onTrustChange} />);

    const checkbox = screen.getByTestId('trusted-source-checkbox');
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(onTrustChange).toHaveBeenCalledWith(true);

    rerender(<PluginTrustedSourceDisclosure trusted={true} onTrustChange={onTrustChange} />);
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    expect(onTrustChange).toHaveBeenCalledWith(false);
  });

  it('respects disabled prop on checkbox', () => {
    render(<PluginTrustedSourceDisclosure trusted={false} onTrustChange={vi.fn()} disabled={true} />);
    expect(screen.getByTestId('trusted-source-checkbox')).toBeDisabled();
  });
});
