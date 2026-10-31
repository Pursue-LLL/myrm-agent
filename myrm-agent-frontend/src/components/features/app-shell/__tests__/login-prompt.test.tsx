/** @vitest-environment jsdom */
import type { ComponentProps } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LoginPrompt from '../login-prompt';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

describe('LoginPrompt', () => {
  it.each(['default', 'compact'] as const)('offers only the real sign-in outside development (%s)', (variant) => {
    render(<LoginPrompt variant={variant} />);

    expect(screen.getByText('auth.login.buttonLogin')).toBeDefined();
    expect(screen.queryByText('userMenu.loginForTest')).toBeNull();
  });

  // The mock login only exists for local development; a caller must not be able to switch it on in a shipped build.
  it('ignores a caller that tries to force the test login on', () => {
    const removedProp = { showTestLogin: true } as unknown as ComponentProps<typeof LoginPrompt>;
    render(<LoginPrompt {...removedProp} />);

    expect(screen.queryByText('userMenu.loginForTest')).toBeNull();
  });
});
