'use client';

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { AgentSetupWizard } from '../AgentSetupWizard';

vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
  useLocale: () => 'en',
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: { error: vi.fn() },
}));

vi.mock('@/components/primitives/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const { mockGetTemplates, mockInstantiateTemplate, mockGetAgentReadiness } = vi.hoisted(() => ({
  mockGetTemplates: vi.fn(),
  mockInstantiateTemplate: vi.fn(),
  mockGetAgentReadiness: vi.fn(),
}));

vi.mock('@/services/agent', () => ({
  getTemplates: mockGetTemplates,
  instantiateTemplate: mockInstantiateTemplate,
  getAgentReadiness: mockGetAgentReadiness,
}));

function template(id: string) {
  return { id, name: `tpl-${id}`, description: `desc-${id}`, agent_type: 'individual' };
}

function report(level: 'ready' | 'warning' | 'blocked') {
  return {
    overall_level: level,
    agent_id: 'a1',
    checked_at: 0,
    items: [{ dimension: 'model', level, reason: 'r', next_action: 'n', settings_path: 's' }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  mockGetTemplates.mockResolvedValue([template('t1')]);
});

async function openWizard() {
  const onOpenChange = vi.fn();
  const onDone = vi.fn();
  render(<AgentSetupWizard open onOpenChange={onOpenChange} onDone={onDone} />);
  await waitFor(() => expect(screen.getByText('tpl-t1')).toBeInTheDocument());
  return { onOpenChange, onDone };
}

describe('AgentSetupWizard', () => {
  it('loads templates on open', async () => {
    await openWizard();
    expect(mockGetTemplates).toHaveBeenCalledTimes(1);
  });

  it('disables continue when readiness is blocked', async () => {
    const user = userEvent.setup();
    mockInstantiateTemplate.mockResolvedValue({ id: 'a1', name: 'A' });
    mockGetAgentReadiness.mockResolvedValue(report('blocked'));
    await openWizard();
    await user.click(screen.getByText('tpl-t1'));
    await waitFor(() => expect(screen.getByText('Agent.setupWizard.actions.continue')).toBeInTheDocument());
    expect(screen.getByText('Agent.setupWizard.actions.continue').closest('button')).toBeDisabled();
    expect(screen.getByText('Agent.setupWizard.readiness.blockedHint')).toBeInTheDocument();
  });

  it('allows continue on warning and finishes the flow', async () => {
    const user = userEvent.setup();
    mockInstantiateTemplate.mockResolvedValue({ id: 'a1', name: 'A' });
    mockGetAgentReadiness.mockResolvedValue(report('warning'));
    const { onDone } = await openWizard();
    await user.click(screen.getByText('tpl-t1'));
    const cont = await screen.findByText('Agent.setupWizard.actions.continue');
    expect(cont.closest('button')).not.toBeDisabled();
    await user.click(cont);
    await user.click(screen.getByText('Agent.setupWizard.actions.finish'));
    await user.click(screen.getByText('Agent.setupWizard.actions.close'));
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem('myrm-agent-setup-wizard-draft')).toBeNull();
  });

  it('skip closes without creating', async () => {
    const user = userEvent.setup();
    const { onOpenChange } = await openWizard();
    await user.click(screen.getByText('Agent.setupWizard.actions.skip'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockInstantiateTemplate).not.toHaveBeenCalled();
  });
});
