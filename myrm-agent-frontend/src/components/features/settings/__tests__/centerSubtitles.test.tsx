/** @vitest-environment jsdom */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

type Messages = Record<string, unknown>;

const LOCALES = ['zh', 'en', 'zh-TW', 'ja', 'ko', 'de'] as const;
type Locale = (typeof LOCALES)[number];

function isRecord(value: unknown): value is Messages {
  return typeof value === 'object' && value !== null;
}

function message(catalog: Messages, path: string): string {
  const value = path.split('.').reduce<unknown>((node, part) => (isRecord(node) ? node[part] : undefined), catalog);
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`Missing message: ${path}`);
  }
  return value;
}

function loadCatalog(locale: Locale): Messages {
  return JSON.parse(readFileSync(resolve(process.cwd(), 'locales', `${locale}.json`), 'utf8')) as Messages;
}

const catalogs = Object.fromEntries(LOCALES.map((locale) => [locale, loadCatalog(locale)])) as Record<Locale, Messages>;

interface MockState {
  params: URLSearchParams;
  resolve: (path: string) => string;
  translator: (namespace?: string) => (key: string) => string;
}

const state = vi.hoisted((): MockState => {
  // One translator per namespace: components may list `t` in hook dependencies, so its identity must stay stable.
  const translators = new Map<string, (key: string) => string>();
  const hoisted: MockState = {
    params: new URLSearchParams(),
    resolve: (path) => path,
    translator: (namespace = '') => {
      let translator = translators.get(namespace);
      if (!translator) {
        translator = (key) => hoisted.resolve(namespace ? `${namespace}.${key}` : key);
        translators.set(namespace, translator);
      }
      return translator;
    },
  };
  return hoisted;
});

// Resolves against the real catalog and throws on a missing path, so a mistyped namespace or key fails the render.
vi.mock('next-intl', () => ({ useTranslations: (namespace?: string) => state.translator(namespace) }));
vi.mock('next/navigation', () => ({ useSearchParams: () => state.params }));
vi.mock('@/hooks/settings/useSettingsSubTabUrl', () => ({
  useSettingsSubTabUrl: () => ({ handleTabChange: vi.fn() }),
  defaultSubTabResolver: () => () => null,
}));
vi.mock('@/lib/deploy-mode', () => ({ isLocalMode: () => true }));
vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: (select: (gate: { isEnabled: () => boolean }) => boolean) => select({ isEnabled: () => true }),
}));
vi.mock('@/components/features/loadout/TeamAssetsHub', () => ({ TeamAssetsHub: () => null }));
vi.mock('@/components/features/message-box/MemoryRecallDegradedBanner', () => ({
  MemoryRecallDegradedBanner: () => null,
}));
vi.mock('@/components/features/memory/settings/MemoryMigrationNotice', () => ({ default: () => null }));
vi.mock('@/components/features/skills/PendingEvolutionsDashboard', () => ({ PendingEvolutionsDashboard: () => null }));
vi.mock('@/components/features/skills/EvolutionRejectionDashboard', () => ({
  EvolutionRejectionDashboard: () => null,
}));
vi.mock('../sections/system/DeveloperSection', () => ({ default: () => null }));
vi.mock('../sections/system/ExperimentalFeaturesSection', () => ({ default: () => null }));
vi.mock('../sections/system/UsageStatisticsSection', () => ({ default: () => null }));
vi.mock('../sections/system/CompanionSection', () => ({ default: () => null }));
vi.mock('../sections/system/ImportExportSection', () => ({ default: () => null }));
vi.mock('../sections/system/SystemSection', () => ({ default: () => null }));
vi.mock('../sections/system/AboutSection', () => ({ default: () => null }));
vi.mock('../sections/system/TrustBadgeCard', () => ({ default: () => null }));
vi.mock('../sections/system/RecoveryGuideCard', () => ({ default: () => null }));
vi.mock('../sections/system/StackUpdatePanel', () => ({ default: () => null }));
vi.mock('../sections/knowledge/MemorySection', () => ({ default: () => null }));
vi.mock('../sections/knowledge/MemoryBackupSection', () => ({ default: () => null }));
vi.mock('../sections/knowledge/RemoteBackupSection', () => ({ default: () => null }));
vi.mock('../sections/knowledge/MigrationWizardSection', () => ({ default: () => null }));
vi.mock('../sections/knowledge/FollowUpsPanel', () => ({ default: () => null }));
vi.mock('../sections/knowledge/MigrationPendingReviewSection', () => ({ default: () => null }));
vi.mock('../sections/ai-tools/SkillsSection', () => ({ default: () => null }));
vi.mock('../sections/ai-tools/CompoundingChecklistSection', () => ({ default: () => null }));
vi.mock('../sections/ai-tools/WorkflowTemplateLibrarySection', () => ({ default: () => null }));
vi.mock('../sections/ai-core/ModelServiceSection', () => ({ default: () => null }));
vi.mock('../sections/ai-core/DefaultModelSection', () => ({ default: () => null }));
vi.mock('../sections/ai-core/ModelOrchestrationPlaybookCard', () => ({ default: () => null }));

import DeveloperCenterSection from '../sections/system/DeveloperCenterSection';
import SystemCenterSection from '../sections/system/SystemCenterSection';
import MemoryCenterSection from '../sections/knowledge/MemoryCenterSection';
import UnifiedSkillsSection from '../sections/ai-tools/UnifiedSkillsSection';
import ModelSettingsSection from '../sections/ai-core/ModelSettingsSection';

/** `?sub=` value (null: the default tab) -> catalog path of the header subtitle that tab must show. */
type TabSubtitle = [sub: string | null, path: string];

interface CenterCase {
  center: string;
  element: () => ReactElement;
  subtitles: TabSubtitle[];
}

const CENTERS: CenterCase[] = [
  {
    center: 'developer',
    element: () => <DeveloperCenterSection />,
    subtitles: [
      [null, 'settings.developerCenter.tabDescriptions.devtools'],
      ['experimental', 'settings.developerCenter.tabDescriptions.experimental'],
      ['usage', 'settings.developerCenter.tabDescriptions.usage'],
      ['companion', 'settings.developerCenter.tabDescriptions.companion'],
      ['importexport', 'settings.developerCenter.tabDescriptions.importExport'],
    ],
  },
  {
    center: 'system',
    element: () => <SystemCenterSection />,
    subtitles: [
      [null, 'settings.systemCenter.tabDescriptions.settings'],
      ['about', 'settings.systemCenter.tabDescriptions.about'],
    ],
  },
  {
    center: 'memory',
    element: () => <MemoryCenterSection />,
    subtitles: [
      [null, 'settings.memoryCenter.tabDescriptions.explorer'],
      ['backup', 'settings.memoryCenter.tabDescriptions.backup'],
      ['cloud-backup', 'settings.memoryCenter.tabDescriptions.cloudBackup'],
      ['follow-ups', 'settings.memoryCenter.tabDescriptions.followUps'],
      ['team-hub', 'settings.memoryCenter.tabDescriptions.teamHub'],
      ['migration', 'settings.memoryCenter.tabDescriptions.migration'],
    ],
  },
  {
    center: 'skills',
    element: () => <UnifiedSkillsSection />,
    subtitles: [
      [null, 'settings.skills.tabSubtitles.inventory'],
      ['pending', 'settings.skills.tabSubtitles.pending'],
      ['rejections', 'settings.skills.tabSubtitles.rejections'],
      ['compounding', 'settings.skills.compounding.subtitle'],
      ['workflowTemplates', 'settings.skills.workflowTemplates.subtitle'],
    ],
  },
  {
    center: 'models',
    element: () => <ModelSettingsSection />,
    subtitles: [
      [null, 'settings.modelCenter.tabDescriptions.providers'],
      ['default', 'settings.modelCenter.tabDescriptions.default'],
    ],
  },
];

const SUBTITLE_PATHS = CENTERS.flatMap((entry) => entry.subtitles.map(([, path]) => path));
const RENDER_CASES = CENTERS.flatMap((entry) =>
  entry.subtitles.map(([sub, path]) => ({
    center: entry.center,
    element: entry.element,
    sub,
    path,
  })),
);

const CJK = /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/;
const CJK_THEN_LATIN_SLASH = /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]\s\/\s[A-Za-z]/;

afterEach(() => {
  cleanup();
  state.params = new URLSearchParams();
});

describe('center page header subtitles', () => {
  it('lists the subtitle of every tab of the five centers', () => {
    expect(SUBTITLE_PATHS).toHaveLength(20);
  });

  describe.each(LOCALES)('%s catalog', (locale) => {
    it.each(SUBTITLE_PATHS)('has a single-language subtitle at %s', (path) => {
      const text = message(catalogs[locale], path);

      expect(text).not.toMatch(CJK_THEN_LATIN_SLASH);
      if (locale === 'en' || locale === 'de') {
        expect(text).not.toMatch(CJK);
      } else {
        expect(text).toMatch(CJK);
      }
      if (locale !== 'en') {
        expect(text).not.toBe(message(catalogs.en, path));
      }
    });
  });

  describe.each(LOCALES)('rendered in %s', (locale) => {
    it.each(RENDER_CASES)('$center center shows the subtitle of tab $sub', ({ element, sub, path }) => {
      state.resolve = (requested) => message(catalogs[locale], requested);
      if (sub !== null) {
        state.params = new URLSearchParams({ sub });
      }

      render(element());

      expect(screen.getByText(message(catalogs[locale], path))).toBeInTheDocument();
    });
  });
});
