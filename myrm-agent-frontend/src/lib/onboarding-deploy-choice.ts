/**
 * [INPUT]
 * - window.localStorage (`myrm-onboarding-deploy-choice`)
 *
 * [OUTPUT]
 * - DeployChoice read/write SSOT for the onboarding deployment step.
 *
 * [POS]
 * 首启去向选择持久化。与连接档案（remote-profiles）同源不同键：本键只记
 * 用户在向导内的去向意图，供 Doctor 与后续步骤分支使用，不做路由。
 */

export type OnboardingDeployChoice = 'local' | 'remote' | 'cloud';

const DEPLOY_CHOICE_KEY = 'myrm-onboarding-deploy-choice';

function isBrowser(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage;
}

export function getOnboardingDeployChoice(): OnboardingDeployChoice | null {
  if (!isBrowser()) {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(DEPLOY_CHOICE_KEY);
    if (raw === 'local' || raw === 'remote' || raw === 'cloud') {
      return raw;
    }
    return null;
  } catch {
    return null;
  }
}

export function setOnboardingDeployChoice(choice: OnboardingDeployChoice): void {
  if (!isBrowser()) {
    return;
  }
  try {
    window.localStorage.setItem(DEPLOY_CHOICE_KEY, choice);
  } catch {
    // ignore quota / private mode
  }
}

export function clearOnboardingDeployChoice(): void {
  if (!isBrowser()) {
    return;
  }
  try {
    window.localStorage.removeItem(DEPLOY_CHOICE_KEY);
  } catch {
    // ignore
  }
}
