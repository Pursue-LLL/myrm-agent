/**
 * @vitest-environment jsdom
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ActionSpaceAccuracyRadar, type Turn1CatalogPreview } from '../ActionSpaceAccuracyRadar';
import en from '../../../../../../locales/en.json';
import zh from '../../../../../../locales/zh.json';
import zhTW from '../../../../../../locales/zh-TW.json';
import ja from '../../../../../../locales/ja.json';
import de from '../../../../../../locales/de.json';

let currentLocale: 'en' | 'zh' = 'en';
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => currentLocale));

const preview = (overrides: Partial<Turn1CatalogPreview> = {}): Turn1CatalogPreview => ({
  inline_count: 10,
  hidden_count: 120,
  overflow_count: 0,
  catalog_tokens: 2780,
  search_mounted: true,
  ...overrides,
});

const renderRadar = (catalogPreview: Turn1CatalogPreview) =>
  render(
    <ActionSpaceAccuracyRadar
      isEvaluating={false}
      accuracyLevel={80}
      isNoiseHigh={false}
      isNoiseCritical={false}
      staleCoreSkillCount={0}
      onSmartPrune={vi.fn()}
      catalogPreview={catalogPreview}
      showTurn1Catalog
    />,
  );

describe('ActionSpaceAccuracyRadar turn-1 catalog preview', () => {
  it('states the real catalog size and never advises disabling search to save tokens', () => {
    currentLocale = 'en';
    renderRadar(preview());

    expect(screen.getByText('10 inline · 120 on demand · search ON · ~2,780 tokens')).toBeDefined();
    expect(screen.queryByText(/203/)).toBeNull();
  });

  it('stays quiet when no core skill was pushed out of the inline budget', () => {
    currentLocale = 'en';
    renderRadar(preview({ overflow_count: 0 }));

    expect(screen.queryByText(/Move rarely used Core skills/)).toBeNull();
  });

  it('explains the overflow with the real counts when core skills exceed the budget', () => {
    currentLocale = 'en';
    renderRadar(preview({ overflow_count: 20, hidden_count: 20 }));

    expect(
      screen.getByText(
        'The first 10 Core skills (alphabetical) fit inline in full. The other 20 are listed by name and loaded on demand. Move rarely used Core skills to Peripheral to make room.',
      ),
    ).toBeDefined();
  });

  it('renders the Chinese copy from the real zh messages', () => {
    currentLocale = 'zh';
    renderRadar(preview({ overflow_count: 3, hidden_count: 3, inline_count: 7 }));

    expect(screen.getByText('7 内联 · 3 按需 · search 开启 · 约 2,780 token')).toBeDefined();
    expect(screen.getByText(/前 7 个（按名称排序）完整内联，其余 3 个仅在目录中列出名称/)).toBeDefined();
  });
});

describe('turn-1 catalog preview copy in every locale', () => {
  const packs = { en, zh, 'zh-TW': zhTW, ja, de };

  it.each(Object.entries(packs))('%s keeps every placeholder the component passes', (_locale, messages) => {
    const radar = messages.agent.configEditor.actionSpaceRadar;

    for (const placeholder of ['{inline}', '{hidden}', '{tokens, number}', '{searchState}']) {
      expect(radar.turn1CatalogSummary).toContain(placeholder);
    }
    for (const placeholder of ['{inline}', '{overflow}']) {
      expect(radar.turn1CatalogOverCapHint).toContain(placeholder);
    }
    expect(radar.turn1CatalogOverCapHint).not.toMatch(/203/);
  });
});
