import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentListItem } from '@/services/agent';
import { expectDefined } from '@/test-utils/expectDefined';
import type { PresetAgent } from '@/types/presetAgent';

const stableT = (key: string) => key;

const mocks = vi.hoisted(() => ({
  locale: 'en',
  isLocal: true,
  agents: [] as AgentListItem[],
  providersReady: false,
  fetchAgents: vi.fn(),
  initProviders: vi.fn(),
  warn: vi.fn(),
}));

vi.mock('next-intl', () => ({ useTranslations: () => stableT, useLocale: () => mocks.locale }));
vi.mock('@/store/useAgentStore', () => ({
  default: (select: (state: { agents: AgentListItem[]; fetchAgents: () => void }) => unknown) =>
    select({ agents: mocks.agents, fetchAgents: mocks.fetchAgents }),
}));
vi.mock('@/store/useProviderStore', () => ({
  default: (select: (state: { isInitialized: boolean; initProviders: () => void }) => unknown) =>
    select({ isInitialized: mocks.providersReady, initProviders: mocks.initProviders }),
}));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => mocks.isLocal,
}));
vi.mock('@/lib/utils/toast', () => ({ toast: { warning: mocks.warn } }));

import { useAgentGallery } from '../useAgentGallery';

const STAMP = '2026-11-09T00:00:00Z';

function listed(id: string, overrides: Partial<AgentListItem> = {}): AgentListItem {
  return { id, name: `Name of ${id}`, created_at: STAMP, updated_at: STAMP, ...overrides };
}

const builtIn = (id: string, overrides: Partial<AgentListItem> = {}) => listed(id, { is_built_in: true, ...overrides });

function mountGallery(
  callbacks: {
    onSelectPreset?: (agent: PresetAgent) => void;
    onSelectCustomAgent?: (agent: AgentListItem) => void;
  } = {},
) {
  return renderHook(() =>
    useAgentGallery({
      onSelectPreset: callbacks.onSelectPreset ?? vi.fn(),
      onSelectCustomAgent: callbacks.onSelectCustomAgent,
    }),
  );
}

describe('useAgentGallery', () => {
  beforeEach(() => {
    mocks.locale = 'en';
    mocks.isLocal = true;
    mocks.agents = [];
    mocks.providersReady = false;
    mocks.fetchAgents.mockReset();
    mocks.initProviders.mockReset();
    mocks.warn.mockReset();
  });

  describe('loading what the list needs', () => {
    it('starts the providers and force-loads the whole agent roster for the gallery', () => {
      mountGallery();

      expect(mocks.initProviders).toHaveBeenCalledTimes(1);
      expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);
      expect(mocks.fetchAgents).toHaveBeenCalledWith(true);
    });

    it('leaves the providers alone when they are already up', () => {
      mocks.providersReady = true;

      mountGallery();

      expect(mocks.initProviders).not.toHaveBeenCalled();
      expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);
    });

    it('does not fetch the agents a second time when the providers finish starting', () => {
      const view = mountGallery();

      mocks.providersReady = true;
      view.rerender();

      expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);
      expect(mocks.initProviders).toHaveBeenCalledTimes(1);
    });
  });

  describe('the built-in agents on offer', () => {
    it('lists the built-in agents as presets and keeps the agents the viewer made apart from them', () => {
      mocks.agents = [builtIn('builtin-general'), listed('my-agent'), builtIn('builtin-coder')];

      const { result } = mountGallery();

      expect(result.current.presetAgents.map((agent) => agent.id)).toEqual(['builtin-general', 'builtin-coder']);
      expect(result.current.customAgents.map((agent) => agent.id)).toEqual(['my-agent']);
    });

    it.each(['builtin-researcher', 'builtin-deep-search'])(
      'keeps the retired built-in agent %s out of both lists',
      (id) => {
        mocks.agents = [builtIn(id), builtIn('builtin-general')];

        const { result } = mountGallery();

        expect(result.current.presetAgents.map((agent) => agent.id)).toEqual(['builtin-general']);
        expect(result.current.customAgents).toEqual([]);
      },
    );

    it('describes a preset by its id, name, icon and availability only, loading the rest on activation', () => {
      mocks.agents = [builtIn('builtin-general', { avatar_url: 'icon:Brain' })];

      const { result } = mountGallery();

      expect(result.current.presetAgents).toEqual([
        {
          id: 'builtin-general',
          name: 'General Assistant',
          category: 'general',
          icon: 'Brain',
          systemPrompt: '',
          skillIds: [],
          isAvailable: true,
        },
      ]);
    });

    it('falls back to the chat icon for an agent without an avatar', () => {
      mocks.agents = [builtIn('builtin-general')];

      expect(mountGallery().result.current.presetAgents[0]?.icon).toBe('MessageCircle');
    });

    it('names a built-in agent in the language of the viewer, and keeps the server name for one it does not know', () => {
      mocks.locale = 'zh';
      mocks.agents = [builtIn('builtin-general'), builtIn('builtin-unlisted', { name: 'Server Name' })];

      const view = mountGallery();

      expect(view.result.current.presetAgents.map((agent) => agent.name)).toEqual(['通用助手', 'Server Name']);

      mocks.locale = 'en';
      view.rerender();

      expect(view.result.current.presetAgents.map((agent) => agent.name)).toEqual(['General Assistant', 'Server Name']);
    });
  });

  describe('the visual command-line agent', () => {
    it.each(['cli_visual', 'builtin-cli_visual'])(
      'is its own category when it comes as %s, and usable on a local install',
      (id) => {
        mocks.agents = [builtIn(id)];

        const { result } = mountGallery();

        expect(result.current.presetAgents).toEqual([
          expect.objectContaining({ id, category: 'cli_visual', isAvailable: true }),
        ]);
      },
    );

    it('is not offered at all on a cloud sandbox', () => {
      mocks.isLocal = false;
      mocks.agents = [builtIn('cli_visual'), builtIn('builtin-general')];

      const { result } = mountGallery();

      expect(result.current.presetAgents.map((agent) => agent.id)).toEqual(['builtin-general']);
    });
  });

  describe('choosing an agent', () => {
    it('selects the preset that was clicked', () => {
      mocks.agents = [builtIn('builtin-general')];
      const onSelectPreset = vi.fn();
      const { result } = mountGallery({ onSelectPreset });
      const preset = result.current.presetAgents[0];
      expectDefined(preset, 'preset');

      result.current.handlePresetClick(preset);

      expect(onSelectPreset).toHaveBeenCalledWith(preset);
      expect(mocks.warn).not.toHaveBeenCalled();
    });

    it('explains why the visual command-line agent cannot be chosen when it is unavailable, and does not select it', () => {
      mocks.agents = [builtIn('cli_visual')];
      const onSelectPreset = vi.fn();
      const { result } = mountGallery({ onSelectPreset });
      const preset = result.current.presetAgents[0];
      expectDefined(preset, 'preset');

      result.current.handlePresetClick({ ...preset, isAvailable: false });

      expect(mocks.warn).toHaveBeenCalledWith('notAvailable', { description: 'tauriModeRequired' });
      expect(onSelectPreset).not.toHaveBeenCalled();
    });

    it('hands the clicked custom agent to the caller', () => {
      const own = listed('my-agent');
      mocks.agents = [own];
      const onSelectCustomAgent = vi.fn();

      mountGallery({ onSelectCustomAgent }).result.current.handleCustomAgentClick(own);

      expect(onSelectCustomAgent).toHaveBeenCalledWith(own);
    });

    it('lets a custom agent be clicked when nobody listens', () => {
      const own = listed('my-agent');
      mocks.agents = [own];

      expect(() => mountGallery().result.current.handleCustomAgentClick(own)).not.toThrow();
    });
  });
});
