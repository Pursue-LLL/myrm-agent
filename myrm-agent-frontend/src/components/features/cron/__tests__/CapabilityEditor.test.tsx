import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { CronJob } from '@/services/cron.types';

import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zhTW from '../../../../../locales/zh-TW.json';
import zh from '../../../../../locales/zh.json';

const locales = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

/** Keys the editor asks the `cron` namespace for, so the locale check follows the toggles it really renders. */
const requestedCronKeys = new Set<string>();

function lookupCopy(node: unknown, key: string): string {
  const value = key
    .split('.')
    .reduce<unknown>((current, part) => (current as Record<string, unknown> | undefined)?.[part], node);
  return typeof value === 'string' ? value : key;
}

const cronT = (key: string): string => {
  requestedCronKeys.add(key);
  return lookupCopy(en.cron, key);
};
const panelT = (key: string): string => key;

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (namespace === 'cron' ? cronT : panelT),
}));

vi.mock('@/services/cron', () => ({
  updateCronJob: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { CapabilityEditor } from '../CapabilityEditor';

function jobWithCapabilities(capabilities: string[]): CronJob {
  const job: Partial<CronJob> = { id: 'job-1', required_capabilities: capabilities, tools_allowed: [] };
  return job as CronJob;
}

describe('CapabilityEditor capability toggles', () => {
  it('shows a stored code-interpreter capability as switched on, under its user-facing name', () => {
    render(<CapabilityEditor job={jobWithCapabilities(['code_interpreter'])} onUpdated={vi.fn()} />);

    const toggle = screen.getByRole('button', { name: en.cron.capability.code_interpreter });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
  });

  it('switches on the capabilities of the devops preset for a job created from it', () => {
    const devops = ['shell_exec', 'file_read', 'file_write', 'code_interpreter'];
    render(<CapabilityEditor job={jobWithCapabilities(devops)} onUpdated={vi.fn()} />);

    for (const id of devops) {
      const toggle = screen.getByRole('button', { name: lookupCopy(en.cron, `capability.${id}`) });
      expect(toggle, id).toHaveAttribute('aria-pressed', 'true');
    }
  });

  it.each(Object.entries(locales))(
    'names and describes every capability the editor offers in %s',
    (_locale, messages) => {
      requestedCronKeys.clear();
      render(<CapabilityEditor job={jobWithCapabilities([])} onUpdated={vi.fn()} />);

      const capabilityIds = [...requestedCronKeys]
        .filter((key) => key.startsWith('capability.'))
        .map((key) => key.slice('capability.'.length));
      expect(capabilityIds).toContain('code_interpreter');
      for (const id of capabilityIds) {
        expect(lookupCopy(messages.cron, `capability.${id}`), `capability.${id}`).not.toBe(`capability.${id}`);
        expect(lookupCopy(messages.cron, `capabilityDesc.${id}`), `capabilityDesc.${id}`).not.toBe(
          `capabilityDesc.${id}`,
        );
      }
    },
  );
});
