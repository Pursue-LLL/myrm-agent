/** @vitest-environment jsdom */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SkillAvailabilityNotice from '../SkillAvailabilityNotice';
import SkillCard from '../SkillCard';
import type { Skill, SkillRequires } from '@/store/skill/types';

const translate = (key: string): string => key;
const stableT = Object.assign(translate, { has: () => true });

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    onClick,
  }: {
    href: string;
    children: React.ReactNode;
    onClick?: (event: React.MouseEvent<HTMLAnchorElement>) => void;
  }) => (
    <a
      href={href}
      onClick={(event) => {
        onClick?.(event);
        // Next's client-side navigation takes over the click, so the browser never follows the href itself.
        event.preventDefault();
      }}
    >
      {children}
    </a>
  ),
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
    requires: { bins: [], env: ['EMAIL_IMAP_HOST'], config: [] },
    // The skills API always sends both lists, empty when the skill declares nothing.
    required_oauth_issuers: [],
    required_mcp_server_ids: [],
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

  it('sends X live search to the model providers where its xAI key is added, never to a key action', () => {
    const skill = buildSkill({
      id: 'x-live-search',
      name: 'x-live-search',
      required_oauth_issuers: ['xai'],
      requires: { bins: [], env: [], config: [] },
      unavailable_reason:
        'Add an xAI provider in Settings → Models & Providers, or connect your SuperGrok token in Settings → Integrations → Credentials',
    });
    render(<SkillAvailabilityNotice skill={skill} onConfigureKeys={vi.fn()} />);

    expect(screen.getByText('card.integrationOAuth.xLiveSearch.unavailable')).toBeTruthy();
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe('/settings/models');
    expect(link.textContent).toBe('card.integrationOAuth.xLiveSearch.connectInSettings');
    expect(screen.queryByRole('button', { name: CONFIGURE })).toBeNull();
  });

  it.each([
    ['x-live-search', '/settings/models', 'card.integrationOAuth.xLiveSearch.connectInSettings'],
    ['google-workspace', '/settings/credentials', 'card.integrationOAuth.googleWorkspace.connectInSettings'],
  ])('keeps guiding %s to its settings page when the catalog declares no account for it', (id, href, label) => {
    const skill = buildSkill({
      id,
      name: id,
      requires: { bins: [], env: [], config: [] },
      unavailable_reason: 'raw reason',
    });
    render(<SkillAvailabilityNotice skill={skill} onConfigureKeys={vi.fn()} />);

    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe(href);
    expect(link.textContent).toBe(label);
    expect(screen.queryByRole('button', { name: CONFIGURE })).toBeNull();
  });

  it('still guides a connection-gated skill when the server sent no reason', () => {
    const skill = buildSkill({
      required_mcp_server_ids: ['github'],
      requires: { bins: [], env: [], config: [] },
      unavailable_reason: null,
    });
    render(<SkillAvailabilityNotice skill={skill} />);

    expect(screen.getByText('card.integrationOAuth.connectionRequired.unavailable')).toBeTruthy();
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe('/settings/agents#loadout');
    expect(link.textContent).toBe(CONFIGURE);
  });

  it('renders nothing for an available skill', () => {
    const { container } = render(<SkillAvailabilityNotice skill={buildSkill({ available: true })} />);

    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for an unavailable skill with no reason and nothing to connect', () => {
    const skill = buildSkill({ requires: { bins: [], env: [], config: [] }, unavailable_reason: null });
    const { container } = render(<SkillAvailabilityNotice skill={skill} />);

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

  it('leaves the skill details closed when the settings link is clicked', () => {
    const onViewDetails = vi.fn();
    const skill = buildSkill({
      required_oauth_issuers: ['google_workspace'],
      requires: { bins: [], env: [], config: [] },
      unavailable_reason: 'Connect google_workspace',
    });
    render(<SkillCard skill={skill} isEnabled={false} onViewDetails={onViewDetails} />);

    fireEvent.click(screen.getByRole('link'));

    expect(onViewDetails).not.toHaveBeenCalled();
  });
});
