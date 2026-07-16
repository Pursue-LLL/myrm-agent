import { afterEach, describe, expect, it, vi } from 'vitest';

import { shouldRedirectToLoginOnAuthFailure } from '../deploy-mode';

describe('shouldRedirectToLoginOnAuthFailure', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns true for sandbox build', () => {
    vi.stubEnv('NEXT_PUBLIC_DEPLOY_MODE', 'sandbox');
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(true);
  });

  it('returns false for local build', () => {
    vi.stubEnv('NEXT_PUBLIC_DEPLOY_MODE', 'local');
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(false);
  });
});
