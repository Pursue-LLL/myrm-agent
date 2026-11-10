import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { displayNameInput, draft, renderEditor, roleSelect, saveButton, user } from './subagentsRender';

vi.mock('@/store/useProviderStore', async () => (await import('./subagentsMocks')).providerStoreMock());
vi.mock('@/components/features/settings/default-model/EnabledModelSelect', async () =>
  (await import('./subagentsMocks')).enabledModelSelectMock(),
);

const TWO_ROLES = {
  researcher: { display_name: 'Researcher', theme_color: 'blue', control_scope: 'leaf' },
  coder: { display_name: 'Coder', theme_color: 'green', control_scope: 'leaf' },
} as const;

const rename = (key: string, name: string) => fireEvent.change(displayNameInput(key), { target: { value: name } });

/** Picks the option whose name starts with `option` (the role options also carry a description). */
async function choose(trigger: HTMLElement, option: string): Promise<void> {
  const pointer = user();
  await pointer.click(trigger);
  await pointer.click(await screen.findByRole('option', { name: new RegExp(`^${option}`) }));
}

describe('SubagentsPanel listing', () => {
  it('explains what to do while there are no roles', () => {
    renderEditor();

    expect(screen.getByText('builtinSpecialistsHint')).toBeInTheDocument();
    expect(screen.getByText('noSubagents')).toBeInTheDocument();
    expect(screen.getByText('noSubagentsDesc')).toBeInTheDocument();
    expect(screen.queryByText('fixValidationErrors')).not.toBeInTheDocument();
  });

  it('shows a card for each role in the order they were configured, and no empty-state text', () => {
    renderEditor(TWO_ROLES);

    expect(screen.queryByText('noSubagents')).not.toBeInTheDocument();
    expect(screen.getAllByRole('textbox').map((field) => (field as HTMLInputElement).value)).toEqual([
      'Researcher',
      'Coder',
    ]);
    expect(screen.getByText('researcher')).toBeInTheDocument();
    expect(screen.getByText('coder')).toBeInTheDocument();
  });
});

describe('SubagentsPanel editing a role', () => {
  it('stores the display name for that role only', () => {
    renderEditor(TWO_ROLES);

    rename('coder', 'Builder');

    expect(draft().roles).toEqual({ ...TWO_ROLES, coder: { ...TWO_ROLES.coder, display_name: 'Builder' } });
    expect(draft().errors).toEqual({ coder: '' });
    expect(saveButton()).toBeEnabled();
  });

  it('accepts a display name of 100 characters and rejects one of 101 until it is shortened', () => {
    renderEditor(TWO_ROLES);

    rename('coder', 'x'.repeat(100));
    expect(screen.queryByText('errorDisplayNameTooLong')).not.toBeInTheDocument();

    rename('coder', 'x'.repeat(101));
    expect(screen.getByText('errorDisplayNameTooLong')).toBeInTheDocument();
    expect(screen.getByText('fixValidationErrors')).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    expect(draft().roles.coder.display_name).toBe('x'.repeat(101));

    rename('coder', 'x'.repeat(100));
    expect(screen.queryByText('errorDisplayNameTooLong')).not.toBeInTheDocument();
    expect(screen.queryByText('fixValidationErrors')).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });

  it('marks only the field that holds the error, and tells what is wrong', () => {
    renderEditor(TWO_ROLES);

    rename('coder', 'x'.repeat(101));

    expect(displayNameInput('coder')).toHaveAttribute('aria-invalid', 'true');
    expect(displayNameInput('coder')).toHaveAccessibleDescription('errorDisplayNameTooLong');
    expect(screen.getByRole('alert')).toHaveTextContent('errorDisplayNameTooLong');
    expect(displayNameInput('researcher')).not.toHaveAttribute('aria-invalid');
    expect(displayNameInput('researcher')).not.toHaveAttribute('aria-describedby');

    rename('coder', 'Coder');

    expect(displayNameInput('coder')).not.toHaveAttribute('aria-invalid');
    expect(displayNameInput('coder')).not.toHaveAttribute('aria-describedby');
  });

  it('keeps the error of one role while another is edited', () => {
    renderEditor(TWO_ROLES);
    rename('coder', 'x'.repeat(101));

    rename('researcher', 'Scholar');

    expect(screen.getByText('errorDisplayNameTooLong')).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    expect(draft().errors).toEqual({ coder: 'errorDisplayNameTooLong', researcher: '' });
  });

  it('changes the role kind of that role only', async () => {
    renderEditor(TWO_ROLES);

    await choose(roleSelect('control-scope', 'coder'), 'subagentRoleCoordinator');

    expect(draft().roles).toEqual({ ...TWO_ROLES, coder: { ...TWO_ROLES.coder, control_scope: 'orchestrator' } });
  });

  it('changes the theme colour of that role only', async () => {
    renderEditor(TWO_ROLES);

    await choose(roleSelect('theme-color', 'researcher'), 'purple');

    expect(draft().roles).toEqual({ ...TWO_ROLES, researcher: { ...TWO_ROLES.researcher, theme_color: 'purple' } });
  });

  it('names the selects for assistive technology through their labels', () => {
    renderEditor({ coder: TWO_ROLES.coder });

    expect(screen.getByLabelText('subagentRole')).toBe(roleSelect('control-scope', 'coder'));
    expect(screen.getByLabelText('subagentThemeColor')).toBe(roleSelect('theme-color', 'coder'));
    expect(screen.getByLabelText('subagentDisplayName')).toBe(displayNameInput('coder'));
  });

  it('routes a model to that role only, and clears it again so the role inherits', async () => {
    renderEditor(TWO_ROLES);
    const pointer = user();

    await pointer.click(screen.getAllByRole('button', { name: 'use-model' })[1]);
    expect(draft().roles).toEqual({ ...TWO_ROLES, coder: { ...TWO_ROLES.coder, model: 'openai_like/deepseek-chat' } });

    await pointer.click(screen.getAllByRole('button', { name: 'inherit-model' })[1]);
    expect(draft().roles).toEqual(TWO_ROLES);
  });
});

describe('SubagentsPanel cards', () => {
  const shownModel = (index: number) =>
    screen.getAllByRole('button', { name: 'use-model' })[index].parentElement?.getAttribute('data-model');

  it('shows the blue theme and the worker role for a role that names neither', () => {
    renderEditor({ helper: {} });

    expect(roleSelect('theme-color', 'helper')).toHaveTextContent('blue');
    expect(roleSelect('control-scope', 'helper')).toHaveTextContent('subagentRoleWorker');
    expect(displayNameInput('helper')).toHaveValue('');
  });

  it('shows the configured theme, role kind and display name', () => {
    renderEditor({ boss: { display_name: 'Boss', theme_color: 'red', control_scope: 'orchestrator' } });

    expect(roleSelect('theme-color', 'boss')).toHaveTextContent('red');
    expect(roleSelect('control-scope', 'boss')).toHaveTextContent('subagentRoleCoordinator');
    expect(displayNameInput('boss')).toHaveValue('Boss');
  });

  it('hands the routed model of each role to its picker, and nothing for a role that inherits', () => {
    renderEditor({ a: { model: 'anthropic/claude-sonnet-4' }, b: {}, c: { model: 'openai_like/deepseek-chat' } });

    expect([shownModel(0), shownModel(1), shownModel(2)]).toEqual([
      'anthropic/claude-sonnet-4',
      '',
      'openai_like/deepseek-chat',
    ]);
  });

  it('treats a stored model without a provider part as inheriting', () => {
    renderEditor({ a: { model: 'deepseek-chat' }, b: { model: '/deepseek-chat' } });

    expect([shownModel(0), shownModel(1)]).toEqual(['', '']);
  });
});

describe('SubagentsPanel deleting a role', () => {
  /** The cards list the roles in draft order, each with a delete button named after the action. */
  const askToDelete = async (key: string) => {
    const index = Object.keys(draft().roles).indexOf(key);
    await user().click(screen.getAllByRole('button', { name: 'deleteSubagent' })[index]);
  };

  it('asks first, and keeps the role when the question is declined', async () => {
    renderEditor(TWO_ROLES);

    await askToDelete('coder');
    expect(await screen.findByText('confirmDeleteSubagent')).toBeInTheDocument();
    await user().click(screen.getByRole('button', { name: 'cancel' }));

    expect(screen.queryByText('confirmDeleteSubagent')).not.toBeInTheDocument();
    expect(Object.keys(draft().roles)).toEqual(['researcher', 'coder']);
  });

  it('keeps the role when the question is dismissed with Escape', async () => {
    renderEditor(TWO_ROLES);

    await askToDelete('coder');
    await screen.findByText('confirmDeleteSubagent');
    await user().keyboard('{Escape}');

    expect(screen.queryByText('confirmDeleteSubagent')).not.toBeInTheDocument();
    expect(Object.keys(draft().roles)).toEqual(['researcher', 'coder']);
  });

  it('removes only the confirmed role', async () => {
    renderEditor(TWO_ROLES);

    await askToDelete('researcher');
    await user().click(await screen.findByRole('button', { name: 'confirm' }));

    expect(screen.queryByText('confirmDeleteSubagent')).not.toBeInTheDocument();
    expect(draft().roles).toEqual({ coder: TWO_ROLES.coder });
  });

  it('shows the empty state again after the last role is removed', async () => {
    renderEditor({ coder: TWO_ROLES.coder });

    await askToDelete('coder');
    await user().click(await screen.findByRole('button', { name: 'confirm' }));

    expect(screen.getByText('noSubagents')).toBeInTheDocument();
  });

  it('lets the editor save again when the role that held the only error is removed', async () => {
    renderEditor(TWO_ROLES);
    rename('coder', 'x'.repeat(101));
    expect(saveButton()).toBeDisabled();

    await askToDelete('coder');
    await user().click(await screen.findByRole('button', { name: 'confirm' }));

    expect(draft().errors).toEqual({});
    expect(screen.queryByText('fixValidationErrors')).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });

  it('keeps the error of another role when a role without errors is removed', async () => {
    renderEditor(TWO_ROLES);
    rename('coder', 'x'.repeat(101));

    await askToDelete('researcher');
    await user().click(await screen.findByRole('button', { name: 'confirm' }));

    expect(draft().errors).toEqual({ coder: 'errorDisplayNameTooLong' });
    expect(saveButton()).toBeDisabled();
  });
});
