import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Agent, CommandBindingConfig } from '@/services/agent';
import { AgentEditForm } from '../AgentEditForm';
import { AGENT_ICON_REGISTRY } from '../agent-icons';

const svc = vi.hoisted(() => ({
  getAgent: vi.fn(),
  createAgent: vi.fn(),
  updateAgent: vi.fn(),
}));
const toastError = vi.hoisted(() => vi.fn());

vi.mock('@/services/agent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/agent')>()),
  getAgent: svc.getAgent,
  createAgent: svc.createAgent,
  updateAgent: svc.updateAgent,
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: { error: toastError, success: vi.fn() } }));
vi.mock('@/services/riskHeldToast', () => ({
  isRiskHeldError: (error: unknown) => error instanceof Error && error.message === 'risk-held',
}));
vi.mock('@/components/agent/CommandBindingsEditor', () => ({
  CommandBindingsEditor: ({
    value,
    onChange,
  }: {
    value: CommandBindingConfig[];
    onChange: (next: CommandBindingConfig[]) => void;
  }) => (
    <button
      type="button"
      data-testid="bindings"
      onClick={() =>
        onChange([...value, { command_name: 'go', skill_ids: ['s1'] }, { command_name: '', skill_ids: [] }])
      }
    >
      bindings:{value.length}
    </button>
  ),
}));

const AGENT: Agent = {
  id: 'a1',
  user_id: 'u1',
  name: 'Reviewer',
  description: 'Reviews code',
  avatar_url: 'icon:bot',
  system_prompt: 'Be strict',
  agent_type: 'team',
  browser_source: 'extension',
  dialog_policy: 'auto_accept',
  session_recording: 'always',
  session_policy: { mode: 'idle', daily_reset_hour: 9, idle_minutes: 30 },
  command_bindings: [{ command_name: 'review', skill_ids: ['s1'] }],
  responsibility_scope: 'Owns reviews',
  owner_label: 'Alice',
  acceptance_criteria: ['a', 'b'],
  created_at: '',
  updated_at: '',
};

const DEFAULT_PAYLOAD = {
  name: 'Bot',
  description: '',
  system_prompt: '',
  avatar_url: '',
  agent_type: 'individual',
  command_bindings: null,
  session_policy: null,
  browser_source: null,
  dialog_policy: null,
  session_recording: null,
  responsibility_scope: null,
  owner_label: null,
  acceptance_criteria: null,
};

beforeAll(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

beforeEach(() => {
  svc.getAgent.mockReset().mockResolvedValue(AGENT);
  svc.createAgent.mockReset().mockResolvedValue(AGENT);
  svc.updateAgent.mockReset().mockResolvedValue(AGENT);
  toastError.mockReset();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const flush = () => act(async () => {});

function renderForm(agentId: string | null = null) {
  const onSaveSuccess = vi.fn();
  const onOpenChange = vi.fn();
  const tree = (id: string | null) => (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AgentEditForm open onOpenChange={onOpenChange} agentId={id} onSaveSuccess={onSaveSuccess} />
    </SWRConfig>
  );
  const view = render(tree(agentId));
  return { ...view, onSaveSuccess, onOpenChange, switchTo: (id: string | null) => view.rerender(tree(id)) };
}

const field = (selector: string) => document.querySelector(selector) as HTMLInputElement;
const type = (selector: string, value: string) => fireEvent.change(field(selector), { target: { value } });
const save = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'save' }));
  await flush();
};
const choose = async (comboboxIndex: number, optionPrefix: string) => {
  fireEvent.click(screen.getAllByRole('combobox')[comboboxIndex]);
  const options = await screen.findAllByRole('option');
  fireEvent.click(options.find((o) => o.textContent?.startsWith(optionPrefix)) as HTMLElement);
  await flush();
};

describe('AgentEditForm create mode', () => {
  it('creates an agent whose default policies are submitted as null', async () => {
    const { onSaveSuccess } = renderForm();
    expect(screen.getByText('create.title')).toBeInTheDocument();
    expect(svc.getAgent).not.toHaveBeenCalled();

    type('#name', 'Bot');
    await save();

    expect(svc.createAgent).toHaveBeenCalledWith(DEFAULT_PAYLOAD);
    expect(svc.updateAgent).not.toHaveBeenCalled();
    expect(onSaveSuccess).toHaveBeenCalledTimes(1);
  });

  it('submits what every section collected', async () => {
    renderForm();
    type('#name', 'Bot');
    type('#description', 'Does things');
    type('#system_prompt', 'Be brief');
    type('#responsibility_scope', '  Owns triage ');
    type('#owner_label', ' Bob ');
    type('#acceptance_criteria', 'first\n\nsecond');
    await choose(0, 'form.agentTypeTeam');
    await choose(1, 'form.browserSourceRemote');
    await choose(2, 'form.dialogPolicyAutoDismiss');
    await choose(3, 'form.sessionRecordingOnFailure');
    fireEvent.click(screen.getByRole('switch'));
    await flush();
    await choose(4, 'form.sessionPolicy.modeIdle');
    type('input[type="number"]', '45');
    fireEvent.click(screen.getByTestId('bindings'));
    fireEvent.click(document.querySelectorAll('div.flex-wrap > button')[1]);
    await save();

    expect(svc.createAgent).toHaveBeenCalledWith({
      name: 'Bot',
      description: 'Does things',
      system_prompt: 'Be brief',
      avatar_url: `icon:${Object.keys(AGENT_ICON_REGISTRY)[1]}`,
      agent_type: 'team',
      command_bindings: [{ command_name: 'go', skill_ids: ['s1'] }],
      session_policy: { mode: 'idle', daily_reset_hour: 4, idle_minutes: 45 },
      browser_source: 'remote',
      dialog_policy: 'auto_dismiss',
      session_recording: 'on_failure',
      responsibility_scope: 'Owns triage',
      owner_label: 'Bob',
      acceptance_criteria: ['first', 'second'],
    });
  });

  it('shows the team hint only for team leaders', async () => {
    renderForm();
    expect(screen.queryByText('form.agentTypeTeamHint')).toBeNull();
    await choose(0, 'form.agentTypeTeam');
    expect(screen.getByText('form.agentTypeTeamHint')).toBeInTheDocument();
  });

  it('marks the selected built-in icon', () => {
    renderForm();
    const icons = [...document.querySelectorAll('div.flex-wrap > button')];
    fireEvent.click(icons[0]);
    expect(icons[0]).toHaveClass('ring-2');
    expect(icons[1]).not.toHaveClass('ring-2');
  });

  it('closes through the cancel button', () => {
    const { onOpenChange } = renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe('AgentEditForm validation', () => {
  it('blocks saving and shows readable errors for invalid fields', async () => {
    renderForm();
    await save();
    const nameError = screen.getByText('Name is required');
    expect(nameError).toHaveClass('text-destructive-text');
    expect(svc.createAgent).not.toHaveBeenCalled();

    type('#name', 'x'.repeat(51));
    type('#description', 'd'.repeat(201));
    type('#system_prompt', 'p'.repeat(10001));
    await save();
    expect(screen.getByText('Name must be less than 50 characters')).toBeInTheDocument();
    expect(screen.getByText('Description must be less than 200 characters')).toHaveClass('text-destructive-text');
    expect(screen.getByText('System prompt is too long')).toHaveClass('text-destructive-text');
    expect(svc.createAgent).not.toHaveBeenCalled();
  });

  it('marks the required name label with the readable destructive token', () => {
    renderForm();
    const asterisk = screen.getByText('*');
    expect(asterisk).toHaveClass('text-destructive-text');
    expect(document.querySelector('.text-destructive')).toBeNull();
  });
});

describe('AgentEditForm save failures', () => {
  it('toasts a failed save and re-enables the form', async () => {
    svc.createAgent.mockRejectedValueOnce(new Error('boom'));
    const { onSaveSuccess } = renderForm();
    type('#name', 'Bot');
    await save();
    expect(toastError).toHaveBeenCalledWith('saveError');
    expect(onSaveSuccess).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'save' })).toBeEnabled();
  });

  it('adds no toast when the risk notice has already been shown', async () => {
    svc.createAgent.mockRejectedValueOnce(new Error('risk-held'));
    renderForm();
    type('#name', 'Bot');
    await save();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('disables saving while the request is in flight', async () => {
    let finish: (agent: Agent) => void = () => {};
    svc.createAgent.mockReturnValueOnce(new Promise<Agent>((resolve) => (finish = resolve)));
    const { onSaveSuccess } = renderForm();
    type('#name', 'Bot');
    await save();
    expect(screen.getByRole('button', { name: 'save' })).toBeDisabled();
    expect(onSaveSuccess).not.toHaveBeenCalled();

    finish(AGENT);
    await flush();
    expect(onSaveSuccess).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'save' })).toBeEnabled();
  });
});

describe('AgentEditForm edit mode', () => {
  it('loads the stored agent into every section and updates it', async () => {
    const { onSaveSuccess } = renderForm('a1');
    await waitFor(() => expect(field('#name')?.value).toBe('Reviewer'));
    expect(screen.getByText('edit.title')).toBeInTheDocument();
    expect(svc.getAgent).toHaveBeenCalledWith('a1', true);
    expect(field('#description').value).toBe('Reviews code');
    expect(field('#system_prompt').value).toBe('Be strict');
    expect(field('#responsibility_scope').value).toBe('Owns reviews');
    expect(field('#owner_label').value).toBe('Alice');
    expect(field('#acceptance_criteria').value).toBe('a\nb');
    expect(screen.getByText('form.agentTypeTeamHint')).toBeInTheDocument();
    expect(screen.getByText('form.browserSourceExtensionWarning')).toBeInTheDocument();
    expect(screen.getByTestId('bindings')).toHaveTextContent('bindings:1');
    expect(field('input[type="number"]').value).toBe('30');

    type('#name', 'Reviewer 2');
    await save();

    expect(svc.updateAgent).toHaveBeenCalledWith('a1', {
      name: 'Reviewer 2',
      description: 'Reviews code',
      system_prompt: 'Be strict',
      avatar_url: 'icon:bot',
      agent_type: 'team',
      command_bindings: [{ command_name: 'review', skill_ids: ['s1'] }],
      session_policy: { mode: 'idle', daily_reset_hour: 9, idle_minutes: 30 },
      browser_source: 'extension',
      dialog_policy: 'auto_accept',
      session_recording: 'always',
      responsibility_scope: 'Owns reviews',
      owner_label: 'Alice',
      acceptance_criteria: ['a', 'b'],
    });
    expect(svc.createAgent).not.toHaveBeenCalled();
    expect(onSaveSuccess).toHaveBeenCalledTimes(1);
  });

  it('submits null when the session policy is switched off', async () => {
    renderForm('a1');
    await waitFor(() => expect(field('#name')?.value).toBe('Reviewer'));
    fireEvent.click(screen.getByRole('switch'));
    await save();
    expect(svc.updateAgent.mock.calls[0][1]).toMatchObject({ session_policy: null });
  });

  it('starts every field from scratch when switching to a new agent', async () => {
    const { switchTo } = renderForm('a1');
    await waitFor(() => expect(field('#name')?.value).toBe('Reviewer'));

    switchTo(null);
    await flush();

    expect(field('#name').value).toBe('');
    expect(field('#responsibility_scope').value).toBe('');
    expect(screen.queryByText('form.agentTypeTeamHint')).toBeNull();
    expect(screen.queryByText('form.browserSourceExtensionWarning')).toBeNull();
    expect(screen.getByTestId('bindings')).toHaveTextContent('bindings:0');

    type('#name', 'Fresh');
    await save();
    expect(svc.createAgent).toHaveBeenCalledWith({ ...DEFAULT_PAYLOAD, name: 'Fresh' });
  });
});
