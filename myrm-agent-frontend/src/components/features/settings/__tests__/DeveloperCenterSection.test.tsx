/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

const searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

// 真实的 `defaultSubTabResolver` 决定标签切换写进 URL 的 `sub`；只把依赖路由与脏状态的 Hook 换成空实现。
vi.mock('@/hooks/settings/useSettingsSubTabUrl', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/settings/useSettingsSubTabUrl')>()),
  useSettingsSubTabUrl: () => ({ handleTabChange: vi.fn() }),
}));

vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: (select: (state: { isEnabled: () => boolean }) => boolean) => select({ isEnabled: () => true }),
}));

vi.mock('../sections/system/DeveloperSection', () => ({ default: () => <div data-testid="devtools" /> }));
vi.mock('../sections/system/ExperimentalFeaturesSection', () => ({
  default: () => <div data-testid="experimental" />,
}));
vi.mock('../sections/system/UsageStatisticsSection', () => ({ default: () => <div data-testid="usage" /> }));
vi.mock('../sections/system/CompanionSection', () => ({ default: () => <div data-testid="companion" /> }));
vi.mock('../sections/system/ImportExportSection', () => ({ default: () => <div data-testid="importexport" /> }));

import { defaultSubTabResolver } from '@/hooks/settings/useSettingsSubTabUrl';
import DeveloperCenterSection from '../sections/system/DeveloperCenterSection';

describe('DeveloperCenterSection', () => {
  beforeEach(() => {
    searchParams.delete('sub');
  });

  // 页内标签切换与侧栏子菜单都把标签 id 原样写成 `?sub=`；页面重读 URL 后必须落回同一个标签，
  // 否则点击后会被弹回「开发者」标签。
  it.each(['devtools', 'experimental', 'usage', 'companion', 'importexport'])(
    'keeps the %s tab selected after its own tab switch is written to the URL',
    (tab) => {
      const sub = defaultSubTabResolver('devtools')(tab);
      if (sub !== null) {
        searchParams.set('sub', sub);
      }
      render(<DeveloperCenterSection />);
      expect(screen.getByTestId(tab)).toBeInTheDocument();
    },
  );

  it.each([
    ['experimentalFeatures', 'experimental'],
    ['usageStatistics', 'usage'],
    ['importExport', 'importexport'],
  ])('opens the matching tab for the alias spelling ?sub=%s', (sub, tab) => {
    searchParams.set('sub', sub);
    render(<DeveloperCenterSection />);
    expect(screen.getByTestId(tab)).toBeInTheDocument();
  });

  it('falls back to the developer tab for an unknown sub-view', () => {
    searchParams.set('sub', 'nonexistent');
    render(<DeveloperCenterSection />);
    expect(screen.getByTestId('devtools')).toBeInTheDocument();
  });
});
