/**
 * @vitest-environment jsdom
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../MigrationDiscoveryBanner', () => ({
  default: () => <div>migration-banner</div>,
}));

import { SystemNoticeButton } from '../SystemNoticeButton';

describe('SystemNoticeButton', () => {
  it('opens the notices popover and triggers the playbook entry', () => {
    const onOpenPlaybook = vi.fn();
    render(<SystemNoticeButton onOpenPlaybook={onOpenPlaybook} />);

    fireEvent.click(screen.getByRole('button', { name: 'open' }));

    expect(screen.getByText('title')).toBeDefined();
    expect(screen.getByText('migration-banner')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'playbook' }));

    expect(onOpenPlaybook).toHaveBeenCalledTimes(1);
  });
});
