import { describe, expect, it } from 'vitest';

describe('shouldRedirectToLoginOnAuthFailure', () => {
  it('returns true for sandbox build', async () => {
    const previous = process.env.NEXT_PUBLIC_DEPLOY_MODE;
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'sandbox';
    const { shouldRedirectToLoginOnAuthFailure } = await import(
      `../deploy-mode?ts=${Date.now()}`
    );
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(true);
    if (previous === undefined) {
      delete process.env.NEXT_PUBLIC_DEPLOY_MODE;
    } else {
      process.env.NEXT_PUBLIC_DEPLOY_MODE = previous;
    }
  });

  it('returns false for local build', async () => {
    const previous = process.env.NEXT_PUBLIC_DEPLOY_MODE;
    process.env.NEXT_PUBLIC_DEPLOY_MODE = 'local';
    const { shouldRedirectToLoginOnAuthFailure } = await import(
      `../deploy-mode?ts=${Date.now() + 1}`
    );
    expect(shouldRedirectToLoginOnAuthFailure()).toBe(false);
    if (previous === undefined) {
      delete process.env.NEXT_PUBLIC_DEPLOY_MODE;
    } else {
      process.env.NEXT_PUBLIC_DEPLOY_MODE = previous;
    }
  });
});
