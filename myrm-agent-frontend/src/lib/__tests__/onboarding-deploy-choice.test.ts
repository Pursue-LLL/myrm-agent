import { describe, expect, it, afterEach } from 'vitest';
import {
  clearOnboardingDeployChoice,
  getOnboardingDeployChoice,
  setOnboardingDeployChoice,
} from '@/lib/onboarding-deploy-choice';

function makeWindow() {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
        removeItem: (k: string) => {
          store.delete(k);
        },
      },
    },
  });
}

describe('onboarding deploy choice', () => {
  const originalWindow = globalThis.window;

  afterEach(() => {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  });

  it('round-trips local/remote/cloud selections', () => {
    makeWindow();
    expect(getOnboardingDeployChoice()).toBeNull();
    setOnboardingDeployChoice('cloud');
    expect(getOnboardingDeployChoice()).toBe('cloud');
    setOnboardingDeployChoice('remote');
    expect(getOnboardingDeployChoice()).toBe('remote');
    clearOnboardingDeployChoice();
    expect(getOnboardingDeployChoice()).toBeNull();
  });

  it('rejects unknown stored values', () => {
    const store = new Map([['myrm-onboarding-deploy-choice', 'mars']]);
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        localStorage: {
          getItem: (k: string) => store.get(k) ?? null,
          setItem: (k: string, v: string) => {
            store.set(k, v);
          },
          removeItem: (k: string) => {
            store.delete(k);
          },
        },
      },
    });
    expect(getOnboardingDeployChoice()).toBeNull();
  });
});
