import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AutoModeSuspendedBanner,
  SmartDeniedBanner,
  SociallyIrreversibleBanner,
  SpendProtectionBanner,
} from '../ApprovalBanners';

vi.mock('next-intl', async () => (await import('./approvalStubs')).nextIntlModule);

afterEach(cleanup);

describe('SpendProtectionBanner', () => {
  it('shows what it explains and the amount with two decimals and its currency', () => {
    render(<SpendProtectionBanner spendConfig={{ amount: 12.5, currency: 'EUR' }} />);

    expect(screen.getByTestId('spend-protection-banner')).toBeDefined();
    expect(screen.getByText('toolApproval.spendProtection.title')).toBeDefined();
    expect(screen.getByText('toolApproval.spendProtection.description')).toBeDefined();
    expect(screen.getByText('toolApproval.spendProtection.amount:')).toBeDefined();
    expect(screen.getByText('12.50 EUR')).toBeDefined();
  });

  it('shows a zero amount rather than leaving it out', () => {
    render(<SpendProtectionBanner spendConfig={{ amount: 0, currency: 'USD' }} />);

    expect(screen.getByText('0.00 USD')).toBeDefined();
  });

  it('leaves the amount row out when the amount is unknown', () => {
    render(<SpendProtectionBanner spendConfig={{ currency: 'USD' }} />);

    expect(screen.queryByText('toolApproval.spendProtection.amount:')).toBeNull();
  });

  it('badges the approval as tamper protected only when it carries an action digest', () => {
    const { rerender } = render(<SpendProtectionBanner spendConfig={{ amount: 1, currency: 'USD' }} />);
    expect(screen.queryByText('toolApproval.spendProtection.tamperProtected')).toBeNull();

    rerender(<SpendProtectionBanner spendConfig={{ amount: 1, currency: 'USD', actionDigest: 'digest-1' }} />);
    expect(screen.getByText('toolApproval.spendProtection.tamperProtected')).toBeDefined();
  });
});

describe('AutoModeSuspendedBanner', () => {
  it('blames the consecutive-run limit when that is the one that was crossed', () => {
    render(<AutoModeSuspendedBanner autoModeSuspendedBreach="consecutive" />);

    expect(screen.getByText('toolApproval.autoModeSuspended.title')).toBeDefined();
    expect(screen.getByText('toolApproval.autoModeSuspended.consecutiveReason')).toBeDefined();
    expect(screen.queryByText('toolApproval.autoModeSuspended.totalReason')).toBeNull();
  });

  it.each(['total', 'anything-else'])('blames the total limit for a "%s" breach', (breach) => {
    render(<AutoModeSuspendedBanner autoModeSuspendedBreach={breach} />);

    expect(screen.getByText('toolApproval.autoModeSuspended.totalReason')).toBeDefined();
    expect(screen.queryByText('toolApproval.autoModeSuspended.consecutiveReason')).toBeNull();
  });
});

describe('SociallyIrreversibleBanner', () => {
  it('warns that the action cannot be taken back', () => {
    render(<SociallyIrreversibleBanner />);

    expect(screen.getByText('toolApproval.sociallyIrreversible.title')).toBeDefined();
    expect(screen.getByText('toolApproval.sociallyIrreversible.description')).toBeDefined();
  });
});

describe('SmartDeniedBanner', () => {
  it('says the safety review refused the action', () => {
    render(<SmartDeniedBanner />);

    expect(screen.getByText('toolApproval.smartDenied.title')).toBeDefined();
  });
});
