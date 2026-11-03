/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../locales/en.json';
import zh from '../../../../locales/zh.json';
import { type LocatorHealedToastTranslator, showLocatorHealedToast } from '../locatorHealedToast';

const toastInfo = vi.hoisted(() => vi.fn());

vi.mock('@/lib/utils/toast', () => ({ toast: { info: toastInfo } }));

async function renderToast(locale: 'en' | 'zh', data: Record<string, unknown>) {
  const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');
  const messages = locale === 'en' ? en : zh;
  const translate = createTranslator({ locale, messages, namespace: 'notifications' });
  const t: LocatorHealedToastTranslator = (key) => translate(key as Parameters<typeof translate>[0]);
  showLocatorHealedToast(data, { t });
  const [content] = toastInfo.mock.calls.at(-1) as [ReactNode];
  render(<>{content}</>);
}

describe('showLocatorHealedToast', () => {
  it('explains the self-healing in English with the old and new locator', async () => {
    await renderToast('en', { old_name: 'Submit', new_name: 'Send', distance: 3.14 });

    expect(screen.getByText('Self-healing activated')).toBeInTheDocument();
    expect(screen.getByText(/recovered a broken locator/)).toBeInTheDocument();
    expect(screen.getByText('Target')).toBeInTheDocument();
    expect(screen.getByText('Submit')).toBeInTheDocument();
    expect(screen.getByText(/Send/)).toBeInTheDocument();
    expect(screen.getByText('Δ 3.1px')).toBeInTheDocument();
  });

  it('explains the self-healing in Chinese', async () => {
    await renderToast('zh', { old_name: 'Submit', new_name: 'Send' });

    expect(screen.getByText('自愈已触发')).toBeInTheDocument();
    expect(screen.getByText('目标')).toBeInTheDocument();
    expect(screen.queryByText('Self-healing activated')).not.toBeInTheDocument();
  });

  it('falls back to a localized unknown name when the event carries no locator names', async () => {
    await renderToast('zh', {});

    expect(screen.getAllByText(/未知/)).toHaveLength(2);
  });
});
