/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api';
import SkillDiscoverTab from '../SkillDiscoverTab';

import type { DiscoverySearchResult } from '@/services/skill';

const toastMock = vi.hoisted(() => vi.fn());
const uninstallMock = vi.hoisted(() => vi.fn());

const DISCOVER_T: Record<string, string> = {
  searchPlaceholder: 'Search skills',
  importUrl: 'Import URL',
  install: 'Install',
  installing: 'Installing',
  installed: 'Installed',
  update: 'Update',
  updateAvailable: 'Update available',
  uninstall: 'Uninstall',
  uninstalling: 'Uninstalling',
  uninstallConfirm: 'Remove this skill?',
  uninstalled: 'Uninstalled',
  uninstallFailed: 'Uninstall failed',
  scanning: 'Scanning',
  previewFailed: 'Preview failed',
  installFailed: 'Install failed',
  forceUninstallTitle: 'Force uninstall?',
  forceUninstallDesc: '{name} is used by {count} other skill(s). Removing it will break them.',
  forceUninstall: 'Force Uninstall',
  scanCancel: 'Cancel',
  noResults: 'No results',
  noResultsDesc: 'Try another keyword',
  browseEmptyTitle: 'Browse skills',
  browseEmptyDesc: 'Search to explore',
  allTags: 'All',
  'source.github': 'GitHub',
};

const stableT = Object.assign(
  (key: string, values?: Record<string, string>): string => {
    const template = DISCOVER_T[key] ?? key;
    if (!values) {
      return template;
    }
    return template.replace(/\{(\w+)\}/g, (_, name: string) => values[name] ?? `{${name}}`);
  },
  { has: (key: string): boolean => key in DISCOVER_T },
);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: toastMock,
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/settings/skills',
}));

vi.mock('@/store/useChatStore', () => ({
  default: () => ({ agentConfig: { agentId: 'builtin-general' } }),
}));

vi.mock('../ScanConfirmDialog', () => ({ default: () => null }));
vi.mock('../SkillUrlImportDialog', () => ({ default: () => null }));
vi.mock('../SkillSourcesPanel', () => ({ default: () => null }));
vi.mock('../SkillRegistryMirrorPanel', () => ({ default: () => null }));

const discoveryHookMock = vi.hoisted(() => ({
  results: [] as DiscoverySearchResult[],
  isSearching: false,
  isInstalling: null,
  isPreviewing: null,
  isUninstalling: null,
  previewResult: null,
  searchError: null,
  installError: null,
  installSuccess: null,
  search: vi.fn(),
  preview: vi.fn(),
  install: vi.fn(),
  uninstall: uninstallMock,
  clearPreview: vi.fn(),
  clearResults: vi.fn(),
}));

vi.mock('@/hooks/agent/useSkillDiscovery', () => ({
  useSkillDiscovery: () => discoveryHookMock,
}));

const installedSkill: DiscoverySearchResult = {
  id: 'github-skill',
  name: 'GitHub Helper',
  description: 'Automates GitHub workflows',
  source: 'github',
  author: 'myrm',
  install_url: 'https://example.com/skills/github-helper',
  install_method: 'clawhub',
  version: '1.2.0',
  stars: 42,
  downloads: 300,
  tags: ['dev'],
  readme_url: null,
  subdirectory: null,
  installed_version: '1.2.0',
  installed_skill_id: 'local::github-helper',
  upgrade_available: false,
};

describe('SkillDiscoverTab force-uninstall flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    discoveryHookMock.results = [installedSkill];
    uninstallMock.mockReset();
  });

  it('surfaces the dependent list and force-uninstalls with force=true on 409', async () => {
    const guardError = new ApiError(
      'Skill is referenced by 2 skills',
      409,
      [],
      undefined,
      'DEPENDENTS_EXIST',
    );
    guardError.data = {
      code: 'DEPENDENTS_EXIST',
      impacted_dependents: ['dep-a', 'dep-b'],
    };
    uninstallMock.mockRejectedValueOnce(guardError).mockResolvedValue({
      success: true,
      skill_id: 'local::github-helper',
      skill_name: 'GitHub Helper',
    });

    render(<SkillDiscoverTab />);

    fireEvent.click(screen.getByRole('button', { name: /Uninstall/ }));
    fireEvent.click(screen.getByRole('button', { name: /^Uninstall$/ }));

    await waitFor(() => {
      expect(screen.getByText('Force uninstall?')).toBeInTheDocument();
    });
    expect(screen.getByText('dep-a')).toBeInTheDocument();
    expect(screen.getByText('dep-b')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Force Uninstall/ }));

    await waitFor(() => {
      expect(uninstallMock).toHaveBeenCalledWith('local::github-helper', true);
    });
    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: 'Uninstalled GitHub Helper' }));
  });

  it('uninstalls directly without a force dialog when no dependents exist', async () => {
    uninstallMock.mockResolvedValue({
      success: true,
      skill_id: 'local::github-helper',
      skill_name: 'GitHub Helper',
    });

    const onInstalled = vi.fn();
    render(<SkillDiscoverTab onInstalled={onInstalled} />);

    fireEvent.click(screen.getByRole('button', { name: /Uninstall/ }));
    fireEvent.click(screen.getByRole('button', { name: /^Uninstall$/ }));

    await waitFor(() => {
      expect(uninstallMock).toHaveBeenCalledWith('local::github-helper');
    });
    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: 'Uninstalled GitHub Helper' }));
    expect(onInstalled).toHaveBeenCalled();
  });
});
