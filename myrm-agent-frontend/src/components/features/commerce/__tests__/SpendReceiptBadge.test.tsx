/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SpendReceiptBadge } from '../SpendReceiptBadge';

describe('SpendReceiptBadge copy', () => {
  it.each([
    ['committed', 'statusCommitted'],
    ['reserved', 'statusReserved'],
    ['refunded', 'statusRefunded'],
    ['rejected', 'statusRejected'],
  ] as const)('renders the translated label for the %s status', (status, label) => {
    render(<SpendReceiptBadge merchantDomain="shop.example" amountCents={1250} status={status} />);

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText('shop.example')).toBeInTheDocument();
  });

  it('marks a committed receipt that carries a ledger hash as verified', () => {
    render(<SpendReceiptBadge merchantDomain="shop.example" amountCents={1250} status="committed" hasEntryHash />);

    expect(screen.getByTitle('hashVerified')).toBeInTheDocument();
  });

  it('does not show the verification dot without a ledger hash', () => {
    render(<SpendReceiptBadge merchantDomain="shop.example" amountCents={1250} status="committed" />);

    expect(screen.queryByTitle('hashVerified')).not.toBeInTheDocument();
  });
});
