import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { draft, renderEditor, user } from './subagentsRender';

vi.mock('@/store/useProviderStore', async () => (await import('./subagentsMocks')).providerStoreMock());
vi.mock('@/components/features/settings/default-model/EnabledModelSelect', async () =>
  (await import('./subagentsMocks')).enabledModelSelectMock(),
);

const CODER = { display_name: 'Coder', theme_color: 'green', control_scope: 'leaf' } as const;

const idField = () => screen.getByLabelText('subagentIdLabel') as HTMLInputElement;
const typeId = (value: string) => fireEvent.change(idField(), { target: { value } });
const dialog = () => screen.getByRole('dialog');
const dialogOpen = () => screen.queryByRole('dialog') !== null;

async function openDialog(): Promise<void> {
  await user().click(screen.getByRole('button', { name: 'addSubagent' }));
  await screen.findByRole('dialog');
}

async function pickPreset(name: string): Promise<void> {
  const pointer = user();
  await pointer.click(within(dialog()).getByRole('combobox'));
  await pointer.click(await screen.findByRole('option', { name }));
}

const confirm = () => user().click(within(dialog()).getByRole('button', { name: 'confirm' }));
const cancel = () => user().click(within(dialog()).getByRole('button', { name: 'cancel' }));

describe('SubagentsPanel add dialog opening', () => {
  it('offers the presets and a field for a custom id, and nothing is added by cancelling', async () => {
    renderEditor();

    await openDialog();

    expect(within(dialog()).getByText('addSubagent')).toBeInTheDocument();
    expect(idField()).toHaveValue('');
    expect(idField()).toHaveAttribute('placeholder', 'subagentIdPlaceholder');
    await cancel();

    expect(dialogOpen()).toBe(false);
    expect(draft().roles).toEqual({});
  });

  it('closes when it is dismissed with Escape, adding nothing', async () => {
    renderEditor();
    await openDialog();
    typeId('half_typed');

    await user().keyboard('{Escape}');

    expect(dialogOpen()).toBe(false);
    expect(draft().roles).toEqual({});
  });

  it('lists the four presets and the custom choice', async () => {
    renderEditor();
    await openDialog();

    await user().click(within(dialog()).getByRole('combobox'));

    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'presetResearcher',
      'presetCoder',
      'presetReviewer',
      'presetAnalyst',
      'customId',
    ]);
  });

  it('starts from a blank dialog every time it is opened', async () => {
    renderEditor();
    await openDialog();
    typeId('Bad Id');
    await confirm();
    expect(screen.getByText('errorIdInvalid')).toBeInTheDocument();
    await cancel();

    await openDialog();

    expect(idField()).toHaveValue('');
    expect(screen.queryByText('errorIdInvalid')).not.toBeInTheDocument();
  });

  it('forgets a chosen preset too', async () => {
    renderEditor();
    await openDialog();
    await pickPreset('presetCoder');
    expect(screen.queryByLabelText('subagentIdLabel')).not.toBeInTheDocument();
    await cancel();

    await openDialog();

    expect(idField()).toHaveValue('');
    expect(within(dialog()).getByRole('combobox')).toHaveTextContent('selectPreset');
  });

  it('is blank again after a role was added', async () => {
    renderEditor();
    await openDialog();
    typeId('my_agent');
    await confirm();

    await openDialog();

    expect(idField()).toHaveValue('');
  });
});

describe('SubagentsPanel adding a preset', () => {
  it.each([
    ['researcher', 'presetResearcher', 'blue'],
    ['coder', 'presetCoder', 'green'],
    ['reviewer', 'presetReviewer', 'purple'],
    ['analyst', 'presetAnalyst', 'orange'],
  ])('adds %s with its name and colour as a worker, and closes the dialog', async (key, name, colour) => {
    renderEditor();
    await openDialog();

    await pickPreset(name);
    await confirm();

    expect(dialogOpen()).toBe(false);
    expect(draft().roles).toEqual({ [key]: { display_name: name, theme_color: colour, control_scope: 'leaf' } });
  });

  it('hides the id field while a preset is chosen and brings it back, empty, for the custom choice', async () => {
    renderEditor();
    await openDialog();
    typeId('typed_first');
    await pickPreset('presetCoder');
    expect(screen.queryByLabelText('subagentIdLabel')).not.toBeInTheDocument();

    await pickPreset('customId');

    expect(idField()).toHaveValue('');
  });

  it('adds the typed id once the custom choice was picked', async () => {
    renderEditor();
    await openDialog();
    await pickPreset('customId');

    typeId('my_agent');
    await confirm();

    expect(Object.keys(draft().roles)).toEqual(['my_agent']);
  });

  it('drops a message when another choice is picked', async () => {
    renderEditor();
    await openDialog();
    typeId('a');
    await confirm();
    expect(screen.getByText('errorIdTooShort')).toBeInTheDocument();

    await pickPreset('customId');

    expect(screen.queryByText('errorIdTooShort')).not.toBeInTheDocument();
  });

  it('adds the chosen preset instead of what was typed before it was chosen', async () => {
    renderEditor();
    await openDialog();
    typeId('typed_first');

    await pickPreset('presetReviewer');
    await confirm();

    expect(Object.keys(draft().roles)).toEqual(['reviewer']);
  });

  it('does not offer a preset that is already configured', async () => {
    renderEditor({ coder: CODER });
    await openDialog();

    await user().click(within(dialog()).getByRole('combobox'));

    const options = screen.getAllByRole('option');
    expect(
      options.filter((option) => option.hasAttribute('data-disabled')).map((option) => option.textContent),
    ).toEqual(['presetCoder']);
    await user().click(screen.getByRole('option', { name: 'presetCoder' }));
    await user().keyboard('{Escape}');
    expect(within(dialog()).getByRole('combobox')).toHaveTextContent('selectPreset');
  });
});

describe('SubagentsPanel adding a custom role', () => {
  it('adds the typed id with a blank name, the default colour and as a worker', async () => {
    renderEditor();
    await openDialog();

    typeId('my_agent-2');
    await confirm();

    expect(dialogOpen()).toBe(false);
    expect(draft().roles).toEqual({ 'my_agent-2': { display_name: '', theme_color: 'blue', control_scope: 'leaf' } });
  });

  it('gives a typed id that names a preset the name and colour of that preset', async () => {
    renderEditor();
    await openDialog();

    typeId('analyst');
    await confirm();

    expect(draft().roles).toEqual({
      analyst: { display_name: 'presetAnalyst', theme_color: 'orange', control_scope: 'leaf' },
    });
  });

  it('accepts ids of 2 and of 50 characters', async () => {
    renderEditor();
    await openDialog();
    typeId('ab');
    await confirm();
    await openDialog();
    typeId('c'.repeat(50));
    await confirm();

    expect(Object.keys(draft().roles)).toEqual(['ab', 'c'.repeat(50)]);
  });

  it('accepts an id that happens to be a property name of every object', async () => {
    renderEditor();
    await openDialog();

    typeId('constructor');
    await confirm();

    expect(Object.keys(draft().roles)).toEqual(['constructor']);
    expect(draft().roles.constructor).toEqual({ display_name: '', theme_color: 'blue', control_scope: 'leaf' });
  });

  it.each([
    ['nothing', '', 'errorIdRequired'],
    ['one character', 'a', 'errorIdTooShort'],
    ['51 characters', 'c'.repeat(51), 'errorIdTooLong'],
    ['a space', 'my agent', 'errorIdInvalid'],
    ['a capital letter', 'Agent', 'errorIdInvalid'],
    ['a dot', 'my.agent', 'errorIdInvalid'],
  ])('refuses %s and keeps the dialog open', async (_label, value, message) => {
    renderEditor();
    await openDialog();

    typeId(value);
    await confirm();

    expect(screen.getByText(message)).toBeInTheDocument();
    expect(dialogOpen()).toBe(true);
    expect(draft().roles).toEqual({});
  });

  it('refuses an id that is already a role', async () => {
    renderEditor({ coder: CODER });
    await openDialog();

    typeId('coder');
    await confirm();

    expect(screen.getByText('errorIdDuplicate')).toBeInTheDocument();
    expect(draft().roles).toEqual({ coder: CODER });
  });

  it('takes the message away as soon as the id is edited', async () => {
    renderEditor();
    await openDialog();
    typeId('a');
    await confirm();
    expect(screen.getByRole('alert')).toHaveTextContent('errorIdTooShort');
    expect(idField()).toHaveAttribute('aria-invalid', 'true');
    expect(idField()).toHaveAccessibleDescription('errorIdTooShort');

    typeId('ab');

    expect(screen.queryByText('errorIdTooShort')).not.toBeInTheDocument();
    expect(idField()).not.toHaveAttribute('aria-invalid');
    expect(idField()).not.toHaveAttribute('aria-describedby');
  });
});
