/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import IncognitoNotice from '../IncognitoNotice';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

afterEach(() => {
  useChatStore.setState({ incognitoMode: false });
});

describe('IncognitoNotice', () => {
  it('stays out of the page while incognito mode is off', () => {
    render(<IncognitoNotice />);

    expect(screen.queryByTestId('incognito-notice')).toBeNull();
  });

  it('states the terms of incognito mode as soon as it is switched on', () => {
    useChatStore.setState({ incognitoMode: true });
    render(<IncognitoNotice />);

    const notice = screen.getByRole('status');
    expect(notice.getAttribute('data-testid')).toBe('incognito-notice');
    expect(notice.textContent).toContain('incognitoMode');
    expect(notice.textContent).toContain('incognitoModeDesc');
  });
});
