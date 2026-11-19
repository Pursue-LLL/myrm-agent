import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { CronJob } from '@/services/cron.types';

import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';

const locales = { en, zh } as const;

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

  it('says what a run with nothing chosen can still do, and only while nothing is chosen', () => {
    const { rerender } = render(<CapabilityEditor job={jobWithCapabilities([])} onUpdated={vi.fn()} />);
    expect(screen.getByText(en.cron.capabilitiesAllHint)).toBeInTheDocument();

    rerender(<CapabilityEditor job={jobWithCapabilities(['shell_exec'])} onUpdated={vi.fn()} />);
    expect(screen.queryByText(en.cron.capabilitiesAllHint)).not.toBeInTheDocument();
  });

  it('clears every chosen capability when the read-only preset is picked', () => {
    render(<CapabilityEditor job={jobWithCapabilities(['shell_exec', 'file_write'])} onUpdated={vi.fn()} />);
    expect(screen.queryByText(en.cron.capabilitiesAllHint)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: en.cron.capPreset.readOnly }));

    expect(screen.getByText(en.cron.capabilitiesAllHint)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: en.cron.capability.shell_exec })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it.each(Object.entries(locales))('labels every preset the editor offers in %s', (_locale, messages) => {
    requestedCronKeys.clear();
    render(<CapabilityEditor job={jobWithCapabilities([])} onUpdated={vi.fn()} />);

    const presetKeys = [...requestedCronKeys].filter((key) => /^(capPreset|toolPreset)\./.test(key));
    expect(presetKeys).toContain('capPreset.readOnly');
    for (const key of presetKeys) {
      expect(lookupCopy(messages.cron, key), key).not.toBe(key);
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
