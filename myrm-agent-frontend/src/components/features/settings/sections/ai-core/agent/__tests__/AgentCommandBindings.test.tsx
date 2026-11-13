/** @vitest-environment jsdom */
'use client';

import { cleanup, render, screen } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AgentCommandBindingsState } from '@/hooks/agent/useAgentCommandBindings';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/services/skill', () => ({ listSkills: vi.fn().mockResolvedValue({ skills: [] }) }));

import { AgentCommandBindings } from '../AgentCommandBindings';

const state = (overrides: Partial<AgentCommandBindingsState>): AgentCommandBindingsState => ({
  unavailable: false,
  status: 'ready',
  bindings: [],
  setBindings: vi.fn(),
  issues: [],
  dirty: false,
  canSave: true,
  saving: false,
  save: vi.fn(),
  ...overrides,
});

const renderCard = (overrides: Partial<AgentCommandBindingsState>) =>
  render(
    <SWRConfig value={{ provider: () => new Map() }}>
      <AgentCommandBindings state={state(overrides)} />
    </SWRConfig>,
  );

afterEach(cleanup);

describe('AgentCommandBindings', () => {
  it('asks to save a new agent first and offers no editor', () => {
    renderCard({ unavailable: true, status: 'idle' });

    expect(screen.getByText('saveFirst')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'add' })).toBeNull();
  });

  it('shows a loading placeholder until the bindings arrive', () => {
    renderCard({ status: 'loading' });

    expect(screen.getByText('loading')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'add' })).toBeNull();
  });

  it('reports a load failure instead of exposing an editor that could overwrite server data', () => {
    renderCard({ status: 'error' });

    expect(screen.getByText('loadFailed')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'add' })).toBeNull();
  });

  it('renders the editor once the bindings are loaded', () => {
    renderCard({ bindings: [{ command_name: 'report', skill_ids: ['skill-a'] }], issues: [null] });

    expect(screen.getByText('title')).toBeTruthy();
    expect(screen.getByText('description')).toBeTruthy();
    expect(screen.getByRole('button', { name: /\/report/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'add' })).toBeTruthy();
  });
});
