/** @vitest-environment jsdom */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SkillAvailabilityNotice from '../SkillAvailabilityNotice';
import SkillCard from '../SkillCard';
import { TooltipProvider } from '@/components/primitives/tooltip';
import type { Skill, SkillRequires } from '@/store/skill/types';

const translate = (key: string): string => key;
const stableT = Object.assign(translate, { has: () => true });

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const CONFIGURE = 'card.integrationOAuth.envSkill.configureInSettings';

function buildSkill(overrides: Partial<Skill>): Skill {
  return {
    id: 'imap-smtp-email',
    name: 'imap-smtp-email',
    description: 'Mail',
    type: 'prebuilt',
    storage_path: '/skills/imap',
    version: '1.0.0',
    category: 'office',
    icon_url: null,
    tags: [],
    is_active: true,
    requires: { bins: [], env: ['EMAIL_IMAP_HOST'], config: [] },
    available: false,
    unavailable_reason: 'Missing: ENV: EMAIL_IMAP_HOST',
    trust: 'installed',
    author: null,
    homepage: null,
    always: false,
    model_invocable: true,
    user_invocable: true,
    primary_env: null,
    security: null,
    user_trusted: false,
    evolution_locked: false,
    has_upstream_update: false,
    traps: [],
    verification_steps: [],
    eval_cases: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const withRequires = (requires: SkillRequires): Skill => buildSkill({ requires });

describe('SkillAvailabilityNotice', () => {
  it('offers an in-place key action for an env-gated skill and never a settings link', () => {
    const onConfigureKeys = vi.fn();
    render(<SkillAvailabilityNotice skill={buildSkill({})} onConfigureKeys={onConfigureKeys} />);

    expect(screen.getByText('card.integrationOAuth.envSkill.unavailable')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: CONFIGURE }));
    expect(onConfigureKeys).toHaveBeenCalledTimes(1);
  });

  it('shows the reason without an action when no handler is provided', () => {
    render(<SkillAvailabilityNotice skill={buildSkill({})} />);

    expect(screen.getByText('card.integrationOAuth.envSkill.unavailable')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows the server reason without a key action when bins are also required', () => {
    render(
      <SkillAvailabilityNotice
        skill={withRequires({ bins: ['gh'], env: ['GH_TOKEN'], config: [] })}
        onConfigureKeys={vi.fn()}
      />,
    );

    expect(screen.getByText('Missing: ENV: EMAIL_IMAP_HOST')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('keeps the settings link for OAuth-gated skills', () => {
    const skill = buildSkill({
      required_oauth_issuers: ['google_workspace'],
      requires: { bins: [], env: [], config: [] },
      unavailable_reason: 'Connect google_workspace',
    });
    render(<SkillAvailabilityNotice skill={skill} onConfigureKeys={vi.fn()} />);

    expect(screen.getByRole('link').getAttribute('href')).toBe('/settings/credentials');
    expect(screen.queryByRole('button', { name: CONFIGURE })).toBeNull();
  });

  it('renders nothing for an available skill', () => {
    const { container } = render(<SkillAvailabilityNotice skill={buildSkill({ available: true })} />);

    expect(container.firstChild).toBeNull();
  });
});

describe('SkillCard availability action', () => {
  it('opens the skill details exactly once when the key action is clicked', () => {
    const onViewDetails = vi.fn();
    const skill = buildSkill({});
    render(<SkillCard skill={skill} isEnabled={false} onViewDetails={onViewDetails} />);

    fireEvent.click(screen.getByRole('button', { name: CONFIGURE }));

    expect(onViewDetails).toHaveBeenCalledTimes(1);
    expect(onViewDetails).toHaveBeenCalledWith(skill);
  });
});

describe('SkillCard quarantine badge', () => {
  it('renders the quarantine badge text from translations', () => {
    const skill = buildSkill({ is_active: false, available: true });
    render(
      <TooltipProvider>
        <SkillCard skill={skill} isEnabled={false} onViewDetails={vi.fn()} />
      </TooltipProvider>,
    );

    expect(screen.getByText('card.quarantined')).toBeTruthy();
    expect(screen.queryByText('Quarantined')).toBeNull();
  });
});
