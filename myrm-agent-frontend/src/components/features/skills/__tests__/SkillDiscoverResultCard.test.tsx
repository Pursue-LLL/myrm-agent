/** @vitest-environment jsdom */

import { fireEvent, render, screen } from '@testing-library/react';
import type { useTranslations } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import type { DiscoverySearchResult } from '@/services/skill';

import { SkillResultCard, TagButton, TranslatedTag } from '../SkillDiscoverResultCard';

const TAG_LABELS: Record<string, string> = { 'tagLabels.dev': 'Developer' };

const stableT = Object.assign((key: string): string => TAG_LABELS[key] ?? key, {
  has: (key: string): boolean => key in TAG_LABELS,
});

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const t = stableT as unknown as ReturnType<typeof useTranslations>;

const SKILL: DiscoverySearchResult = {
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
  tags: ['dev', 'misc'],
  readme_url: 'https://example.com/readme',
  subdirectory: null,
  installed_version: null,
  installed_skill_id: null,
  upgrade_available: false,
};

interface CardOverrides {
  skill?: Partial<DiscoverySearchResult>;
  isInstalling?: boolean;
  isPreviewing?: boolean;
  isUninstalling?: boolean;
  justInstalled?: boolean;
}

function renderCard(overrides: CardOverrides = {}) {
  const onInstall = vi.fn();
  const onUninstall = vi.fn();
  const skill = { ...SKILL, ...overrides.skill };
  render(
    <SkillResultCard
      skill={skill}
      isInstalling={overrides.isInstalling ?? false}
      isPreviewing={overrides.isPreviewing ?? false}
      isUninstalling={overrides.isUninstalling ?? false}
      justInstalled={overrides.justInstalled ?? false}
      onInstall={onInstall}
      onUninstall={onUninstall}
      t={t}
    />,
  );
  return { skill, onInstall, onUninstall };
}

describe('SkillResultCard', () => {
  it('shows the skill details with translated tags, stars and a README link', () => {
    renderCard();

    expect(screen.getByText('GitHub Helper')).toBeInTheDocument();
    expect(screen.getByText('source.github')).toBeInTheDocument();
    expect(screen.getByText('Automates GitHub workflows')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Developer')).toBeInTheDocument();
    expect(screen.getByText('misc')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /README/ })).toHaveAttribute('href', 'https://example.com/readme');
  });

  it('installs a skill that is not installed yet', () => {
    const { skill, onInstall } = renderCard();

    fireEvent.click(screen.getByRole('button', { name: 'install' }));

    expect(onInstall).toHaveBeenCalledWith(skill);
    expect(screen.queryByRole('button', { name: /uninstall/ })).not.toBeInTheDocument();
  });

  it.each([
    ['scanning', { isPreviewing: true }],
    ['installing', { isInstalling: true }],
    ['updating', { isInstalling: true, skill: { upgrade_available: true } }],
    ['installed', { justInstalled: true }],
  ])('labels the busy state %s and blocks the action', (label, overrides: CardOverrides) => {
    renderCard(overrides);

    expect(screen.getByRole('button', { name: label })).toBeDisabled();
  });

  it('offers an update, with the version change, when a newer market version exists', () => {
    const { skill, onInstall } = renderCard({
      skill: { installed_version: '1.0.0', installed_skill_id: 'local::gh', upgrade_available: true },
    });

    expect(screen.getByText('updateAvailable')).toBeInTheDocument();
    expect(screen.getByText(/v1\.0\.0 → v1\.2\.0/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'update' }));
    expect(onInstall).toHaveBeenCalledWith(skill);
    expect(screen.queryByRole('button', { name: /uninstall/ })).not.toBeInTheDocument();
  });

  it('uninstalls an installed skill with the destructive text colour', () => {
    const { skill, onUninstall } = renderCard({
      skill: { installed_version: '1.2.0', installed_skill_id: 'local::gh' },
    });

    const button = screen.getByRole('button', { name: /uninstall/ });
    expect(button).toHaveClass('text-destructive-text');
    fireEvent.click(button);

    expect(onUninstall).toHaveBeenCalledWith(skill);
  });

  it('disables uninstalling while another action is running', () => {
    renderCard({ skill: { installed_version: '1.2.0', installed_skill_id: 'local::gh' }, isUninstalling: true });

    expect(screen.getByRole('button', { name: 'uninstalling' })).toBeDisabled();
  });

  it('labels plugin packages and well-known sources', () => {
    renderCard({ skill: { package_type: 'agent_plugin', source: 'well-known:https://example.com/skills' } });

    expect(screen.getByText('Plugin')).toBeInTheDocument();
    expect(screen.getByText('example.com/skills')).toBeInTheDocument();
  });
});

describe('TagButton and TranslatedTag', () => {
  it('marks the active tag and reports clicks', () => {
    const onClick = vi.fn();
    render(
      <TagButton active onClick={onClick}>
        all
      </TagButton>,
    );

    const button = screen.getByRole('button', { name: 'all' });
    expect(button).toHaveClass('bg-primary');
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('shows the translated label when one exists and the raw tag otherwise', () => {
    render(
      <>
        <TranslatedTag tag="Dev" />
        <TranslatedTag tag="custom-tag" />
      </>,
    );

    expect(screen.getByText('Developer', { exact: false })).toBeInTheDocument();
    expect(screen.getByText('custom-tag', { exact: false })).toBeInTheDocument();
  });
});
